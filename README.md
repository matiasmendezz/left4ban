# 🛡️ Left 4 Ban

[![Build Executables](https://github.com/matias/left4ban/actions/workflows/build-executables.yml/badge.svg)](https://github.com/matias/left4ban/actions/workflows/build-executables.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

*Bilingual Documentation: [Español](#español) | [English](#english)*

---

<a name="español"></a>
## 🇪🇸 Español

**Left 4 Ban** es una herramienta integral de escaneo en tiempo real y detección de sanciones/trampas para la comunidad competitiva de **Left 4 Dead 2**. Permite analizar lobbies completos mediante el comando `status` de la consola del juego, perfiles individuales o listas de SteamIDs.

### ✨ Características Principales

- **Multi-Fuente de Detección:**
  - **SirPlease:** Consulta en tiempo real de registros y bans en SourceBans.
  - **L4D2Center:** Detección de bans y sanciones automáticas por abandono (*AutoBans*) con evasión silenciosa de Cloudflare Turnstile.
  - **CedaPug:** Extracción de sanciones y reportes de la liga CedaPug.
- **Metadatos Detallados de Steam:**
  - Resolución inteligente de formatos: SteamID64, SteamID2 (`STEAM_1:X:Y`), SteamID3 (`[U:1:X]`) y URLs vanity personalizadas.
  - Estimación de antigüedad de cuenta calculada a partir del SteamID2.
  - Horas totales jugadas en Left 4 Dead 2 e indicador de perfil privado.
  - Historial de nombres/alias recientes.
  - Detección de cuentas secundarias (*smurfs*).
  - Botón de copiado rápido de SteamID2 al portapapeles.
- **Barra de Acciones de Lobby y Reportes:**
  - Filtro para ocultar/mostrar autobans expirados.
  - Exportación con un clic para el chat de L4D2 (`say ...`) respetando los límites de caracteres del juego.
  - Exportación formateada para canales de Discord.
- **Escaneo en Vivo con SSE (Server-Sent Events):** Los resultados se actualizan en pantalla a medida que se procesa cada jugador sin necesidad de recargar la página.

---

### 🚀 Formas de Uso

#### Opción 1: Ejecutable Autónomo (Recomendado para usuarios finales)
No requiere tener Python instalado. Descarga el ejecutable desde [Releases](../../releases) y ejecútalo con doble clic:
- **Windows:** Ejecuta `Left4Ban.exe` o `run_left4ban.bat`.
- **Linux:** Ejecuta `./dist/Left4Ban` o `./run_left4ban.sh`.

La aplicación iniciará automáticamente el servidor local y abrirá la interfaz web en tu navegador predeterminado (`http://127.0.0.1:5000`).

#### Opción 2: Desde el Código Fuente (Python)
Requisitos: Python 3.10+ y un navegador basado en Chromium (Google Chrome, Brave o Edge).

1. Clonar el repositorio:
   ```bash
   git clone https://github.com/matias/left4ban.git
   cd left4ban
   ```
2. Crear y activar un entorno virtual:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # En Windows: .venv\Scripts\activate
   ```
3. Instalar dependencias:
   ```bash
   pip install -r requirements.txt
   ```
4. (Opcional) Configurar tu Steam Web API Key para obtener metadatos completos y avatares:
   ```bash
   export STEAM_API_KEY="TU_API_KEY_DE_STEAM"  # En Windows: set STEAM_API_KEY=TU_API_KEY_DE_STEAM
   ```
5. Iniciar la aplicación:
   ```bash
   ./run_left4ban.sh  # En Windows: run_left4ban.bat
   # O directamente:
   python app.py
   ```

#### Opción 3: Contenedor Docker
```bash
# Construir la imagen
docker build -t left4ban .

# Ejecutar el contenedor
docker run -d -p 5000:5000 -e STEAM_API_KEY="TU_API_KEY" --name left4ban left4ban
```
Accede desde tu navegador a `http://localhost:5000`.

---

### 📦 Compilación del Ejecutable Autónomo

Para generar tu propio binario único:
```bash
pip install pyinstaller
python build_executable.py
```
El archivo resultante se generará en la carpeta `dist/` (`Left4Ban.exe` en Windows o `Left4Ban` en Linux).

---
---

<a name="english"></a>
## 🇬🇧 English

**Left 4 Ban** is a comprehensive, real-time ban and player inspection scanner tailored for the competitive **Left 4 Dead 2** community. Analyze entire lobbies simply by pasting the output of the console `status` command, individual profile links, or lists of SteamIDs.

### ✨ Key Features

- **Multi-Source Ban Aggregation:**
  - **SirPlease:** Live SourceBans queries and infraction logs.
  - **L4D2Center:** Ban detection and automatic leaver infractions (*AutoBans*) with seamless Cloudflare Turnstile bypass.
  - **CedaPug:** Sanction extraction and competitive league reports.
- **Enriched Steam Player Metadata:**
  - Versatile identifier parsing: SteamID64, SteamID2 (`STEAM_1:X:Y`), SteamID3 (`[U:1:X]`), and custom vanity URLs.
  - Account age estimation calculated from SteamID2 sequence.
  - Total hours logged in Left 4 Dead 2 plus indicators for private profiles.
  - Recent Steam vanity aliases.
  - Smurf account detection linked to primary profiles.
  - Instant SteamID2 clipboard copy button.
- **Lobby Action Bar & Report Export Tools:**
  - Interactive toggle to hide or display expired autobans.
  - One-click copy for in-game L4D2 chat (`say ...`) optimized for in-game character limits.
  - One-click Discord markdown lobby report generator.
- **Real-Time SSE Streaming:** Player cards render dynamically as queries complete without full-page reloads.

---

### 🚀 Getting Started

#### Option 1: Standalone Single-File Executable (Recommended)
No Python installation required. Download the pre-built release from [Releases](../../releases) and launch:
- **Windows:** Double-click `Left4Ban.exe` or `run_left4ban.bat`.
- **Linux:** Run `./dist/Left4Ban` or `./run_left4ban.sh`.

Left 4 Ban automatically starts a local server and opens your default browser at `http://127.0.0.1:5000`.

#### Option 2: Running from Source
Prerequisites: Python 3.10+ and a Chromium-based browser (Google Chrome, Brave, or Microsoft Edge).

1. Clone the repository:
   ```bash
   git clone https://github.com/matias/left4ban.git
   cd left4ban
   ```
2. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. (Optional) Set your Steam Web API Key:
   ```bash
   export STEAM_API_KEY="YOUR_STEAM_API_KEY"  # On Windows: set STEAM_API_KEY=YOUR_STEAM_API_KEY
   ```
5. Launch the application:
   ```bash
   ./run_left4ban.sh  # On Windows: run_left4ban.bat
   # Or directly:
   python app.py
   ```

#### Option 3: Docker Container
```bash
# Build Docker image
docker build -t left4ban .

# Run Docker container
docker run -d -p 5000:5000 -e STEAM_API_KEY="YOUR_STEAM_API_KEY" --name left4ban left4ban
```
Open `http://localhost:5000` in your web browser.

---

### 📦 Building the Standalone Executable

To bundle the application into a single executable binary:
```bash
pip install pyinstaller
python build_executable.py
```
The output binary will be created in `dist/` (`Left4Ban.exe` on Windows, `Left4Ban` on Linux).

---

### 📄 License

This project is licensed under the MIT License.
