import io
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
import pandas as pd
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

SECRET_KEY = "cambia-esta-clave-secreta-en-produccion"
ALGORITHM = "HS256"
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"
DB_PATH = "database.db"

app = FastAPI(title="Explorador Normativo Tributario API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# --- SERVIR EL FRONTEND ESTÁTICO (Para la nube y uso local unificado) ---
# Si colocas tu carpeta 'frontend' dentro de 'backend', esto montará la interfaz en /app/index.html
if os.path.exists("frontend"):
    app.mount("/app", StaticFiles(directory="frontend", html=True), name="frontend")


class LoginRequest(BaseModel):
    username: str
    password: str


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria TEXT,
            codigo_dane TEXT,
            departamento TEXT,
            municipio TEXT,
            acuerdo TEXT,
            anio_actualizacion TEXT,
            articulo TEXT,
            pagina TEXT,
            definicion TEXT,
            presencia_ausencia TEXT,
            detalle_json TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_depto ON registros(departamento)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_muni ON registros(municipio)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cat ON registros(categoria)")
    conn.commit()
    conn.close()


@app.on_event("startup")
def startup_event():
    init_db()


def create_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": datetime.now(timezone.utc) + timedelta(hours=8),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión expirada")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")


@app.post("/api/login")
def login(data: LoginRequest):
    if data.username == ADMIN_USER and data.password == ADMIN_PASS:
        return {"access_token": create_token(data.username), "token_type": "bearer"}
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario o contraseña incorrectos")


def parse_matriz_sheet(df_raw: pd.DataFrame, sheet_name: str) -> list[dict]:
    header_idx = None
    for idx in range(min(20, len(df_raw))):
        row_values = [str(v).strip().lower() for v in df_raw.iloc[idx].tolist()]
        if "departamento" in row_values and "municipio" in row_values:
            header_idx = idx
            break

    if header_idx is None:
        return []

    raw_headers = [
        str(col).strip().replace("\n", " ") if pd.notna(col) else f"Col_{i}"
        for i, col in enumerate(df_raw.iloc[header_idx])
    ]

    seen = {}
    unique_headers = []
    for h in raw_headers:
        if h in seen:
            seen[h] += 1
            unique_headers.append(f"{h}_{seen[h]}")
        else:
            seen[h] = 0
            unique_headers.append(h)

    df_data = df_raw.iloc[header_idx + 1 :].copy()
    df_data.columns = unique_headers

    if "Municipio" not in df_data.columns or "Departamento" not in df_data.columns:
        return []

    df_data = df_data[df_data["Municipio"].notna() & df_data["Departamento"].notna()]
    df_data = df_data[~df_data["Departamento"].astype(str).str.lower().isin(["total si", "total no", "r", "nan", ""])]

    records = []
    for _, row in df_data.iterrows():
        depto = str(row.get("Departamento", "")).strip()
        muni = str(row.get("Municipio", "")).strip()
        if not depto or not muni:
            continue

        detalle = {}
        for col_name, val in row.items():
            if pd.notna(val) and str(val).strip() != "" and not col_name.startswith("Col_"):
                clean_name = col_name.split("_")[0]
                detalle[clean_name] = str(val).strip()

        anio_raw = str(row.get("Año de actualización", "")).strip()
        if anio_raw.endswith(".0"):
            anio_raw = anio_raw[:-2]

        dane_raw = str(row.get("Código Dane", "")).strip()
        if dane_raw.endswith(".0"):
            dane_raw = dane_raw[:-2]

        records.append({
            "categoria": sheet_name,
            "codigo_dane": dane_raw,
            "departamento": depto.title(),
            "municipio": muni.title(),
            "acuerdo": str(row.get("Acuerdo", "")).strip() if pd.notna(row.get("Acuerdo")) else "",
            "anio_actualizacion": anio_raw if anio_raw.lower() != "nan" else "",
            "articulo": str(row.get("Art.", "")).strip() if pd.notna(row.get("Art.")) else "",
            "pagina": str(row.get("Pág.", "")).strip() if pd.notna(row.get("Pág.")) else "",
            "definicion": str(row.get("Definición", "")).strip() if pd.notna(row.get("Definición")) else "",
            "presencia_ausencia": (
                str(row.get("Presencia / Ausencia", "")).strip()
                if pd.notna(row.get("Presencia / Ausencia"))
                else "N/A"
            ),
            "detalle_json": json.dumps(detalle, ensure_ascii=False),
        })
    return records


@app.post("/api/admin/upload")
async def upload_dataset(
    file: UploadFile = File(...),
    mode: str = Form("replace"),
    _user: str = Depends(verify_token),
):
    filename = file.filename.lower()
    if not (filename.endswith(".xlsx") or filename.endswith(".xls") or filename.endswith(".csv")):
        raise HTTPException(status_code=400, detail="Formato no soportado.")

    content = await file.read()
    all_records = []

    try:
        if filename.endswith(".csv"):
            df_raw = pd.read_csv(io.BytesIO(content), header=None)
            all_records.extend(parse_matriz_sheet(df_raw, "General"))
        else:
            excel_file = pd.ExcelFile(io.BytesIO(content))
            for sheet in excel_file.sheet_names:
                df_raw = pd.read_excel(excel_file, sheet_name=sheet, header=None)
                all_records.extend(parse_matriz_sheet(df_raw, sheet))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al procesar el archivo: {str(e)}")

    if not all_records:
        raise HTTPException(status_code=400, detail="No se encontraron registros válidos.")

    conn = get_db()
    cursor = conn.cursor()

    if mode == "replace":
        cursor.execute("DELETE FROM registros")

    cursor.executemany(
        """
        INSERT INTO registros (
            categoria, codigo_dane, departamento, municipio, acuerdo,
            anio_actualizacion, articulo, pagina, definicion, presencia_ausencia, detalle_json
        ) VALUES (
            :categoria, :codigo_dane, :departamento, :municipio, :acuerdo,
            :anio_actualizacion, :articulo, :pagina, :definicion, :presencia_ausencia, :detalle_json
        )
        """,
        all_records,
    )
    conn.commit()
    total_db = cursor.execute("SELECT COUNT(*) FROM registros").fetchone()[0]
    conn.close()

    return {
        "message": "Carga exitosa.",
        "registros_procesados": len(all_records),
        "total_en_base_datos": total_db,
    }


@app.get("/api/filters")
def get_filter_options(departamento: Optional[str] = None):
    conn = get_db()
    cursor = conn.cursor()
    departamentos = [
        r[0] for r in cursor.execute("SELECT DISTINCT departamento FROM registros WHERE departamento != '' ORDER BY departamento").fetchall()
    ]
    if departamento:
        municipios = [
            r[0]
            for r in cursor.execute(
                "SELECT DISTINCT municipio FROM registros WHERE departamento = ? AND municipio != '' ORDER BY municipio",
                (departamento,),
            ).fetchall()
        ]
    else:
        municipios = [
            r[0] for r in cursor.execute("SELECT DISTINCT municipio FROM registros WHERE municipio != '' ORDER BY municipio").fetchall()
        ]
    categorias = [
        r[0] for r in cursor.execute("SELECT DISTINCT categoria FROM registros WHERE categoria != '' ORDER BY categoria").fetchall()
    ]
    anios = [
        r[0]
        for r in cursor.execute(
            "SELECT DISTINCT anio_actualizacion FROM registros WHERE anio_actualizacion != '' ORDER BY anio_actualizacion DESC"
        ).fetchall()
    ]
    presencias = [
        r[0]
        for r in cursor.execute(
            "SELECT DISTINCT presencia_ausencia FROM registros WHERE presencia_ausencia != '' ORDER BY presencia_ausencia"
        ).fetchall()
    ]
    conn.close()
    return {
        "departamentos": departamentos,
        "municipios": municipios,
        "categorias": categorias,
        "anios": anios,
        "presencias": presencias,
    }


@app.get("/api/records")
def search_records(
    q: Optional[str] = None,
    departamento: Optional[str] = None,
    municipio: Optional[str] = None,
    categoria: Optional[str] = None,
    anio: Optional[str] = None,
    presencia: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    conn = get_db()
    cursor = conn.cursor()
    conditions, params = [], []
    if departamento:
        conditions.append("departamento = ?")
        params.append(departamento)
    if municipio:
        conditions.append("municipio = ?")
        params.append(municipio)
    if categoria:
        conditions.append("categoria = ?")
        params.append(categoria)
    if anio:
        conditions.append("anio_actualizacion = ?")
        params.append(anio)
    if presencia:
        conditions.append("presencia_ausencia = ?")
        params.append(presencia)
    if q:
        conditions.append(
            "(municipio LIKE ? OR departamento LIKE ? OR acuerdo LIKE ? OR definicion LIKE ? OR detalle_json LIKE ?)"
        )
        like_q = f"%{q}%"
        params.extend([like_q, like_q, like_q, like_q, like_q])

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    total = cursor.execute(f"SELECT COUNT(*) FROM registros {where_clause}", params).fetchone()[0]
    offset = (page - 1) * page_size
    rows = cursor.execute(
        f"""
        SELECT id, categoria, codigo_dane, departamento, municipio, acuerdo,
               anio_actualizacion, articulo, pagina, definicion, presencia_ausencia, detalle_json
        FROM registros
        {where_clause}
        ORDER BY departamento, municipio, id
        LIMIT ? OFFSET ?
        """,
        (*params, page_size, offset),
    ).fetchall()
    conn.close()

    results = []
    for r in rows:
        item = dict(r)
        item["detalle"] = json.loads(item.pop("detalle_json") or "{}")
        results.append(item)

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
        "items": results,
    }


# Ejecución local de respaldo respetando puertos en la nube
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)