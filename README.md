# Explorador Tributario Municipal (ICA)

Proyecto final de Ingeniería del Software - Universidad Industrial de Santander (UIS).  
Aplicación full-stack interactiva para la consulta de acuerdos, tarifas, territorialidad y economía digital del Impuesto de Industria y Comercio (ICA), construida con **FastAPI** (backend) y **HTML/Tailwind CSS** (frontend), con despliegue automático en **Render**.

---

## Guía de Colaboración para el Equipo

Si eres colaborador del repositorio y deseas realizar cambios en el código, diseño o visualizaciones, sigue estos pasos en tu computadora:

### 1. Requisitos Previos
Asegúrate de tener instalado en tu equipo:
* [Git](https://git-scm.com/)
* [Python](https://www.python.org/) (Versión 3.10 o superior)

### 2. Clonar el Repositorio
Abre tu terminal (o consola) y descarga el proyecto ejecutando:

```bash
git clone [https://github.com/X10Andres10X/explorador-tributario.git](https://github.com/X10Andres10X/explorador-tributario.git)
cd explorador-tributario
```

### 3. Configurar el Entorno Local (Backend)
Es altamente recomendable crear un entorno virtual para trabajar de manera aislada:

```bash
# Crear el entorno virtual
python -m venv backend/venv

# Activar el entorno virtual:
# En Windows (PowerShell):
backend\venv\Scripts\Activate.ps1
# En Mac / Linux:
source backend/venv/bin/activate

# Instalar las dependencias del proyecto
pip install -r backend/requirements.txt
```

### 4. Ejecutar el Servidor en Local
Para probar la aplicación localmente en tu computadora:

```bash
# Entra a la carpeta del backend y arranca el servidor
cd backend
python main.py
```

* Abre tu navegador e ingresa a: `http://localhost:8000`
* **Credenciales de administrador (local y producción):** Usuario `admin` / Contraseña `admin123`

---

## Estructura del Proyecto

* **`backend/`**: Contiene la lógica de la API en FastAPI (`main.py`), la base de datos SQLite (`database.db`) y las dependencias (`requirements.txt`).
* **`frontend/`**: Contiene las interfaces de usuario web estáticas:
  * `index.html`: Buscador público principal y filtros dinámicos.
  * `login.html`: Pantalla de acceso para administradores.
  * `admin.html`: Panel de gestión para subir o actualizar datasets en formato `.xlsx` o `.csv`.

---

## Cómo Subir tus Cambios (Workflow de Git)

Antes de empezar a editar, asegúrate siempre de descargar los últimos cambios que hayan subido otros compañeros:

```bash
git pull origin main
```

Una vez que modifiques archivos (por ejemplo, el diseño o visualizaciones en la carpeta `frontend/`), sube tus aportes al repositorio principal siguiendo este flujo:

```bash
# 1. Verifica los archivos modificados
git status

# 2. Añade los cambios
git add .

# 3. Crea un commit descriptivo
git commit -m "Descripción clara de tu cambio o mejora en la interfaz"

# 4. Sube los cambios a GitHub
git push origin main
```

**Nota importante:** Una vez que hagas el `git push`, **Render detectará automáticamente el cambio** y actualizará la página web en la nube (`https://explorador-tributario-ica.onrender.com`) en cuestión de segundos de forma totalmente autónoma.