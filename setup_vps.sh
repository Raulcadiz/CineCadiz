#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════
# setup_vps.sh — Instala y configura CineCadiz en Ubuntu VPS
# Ejecutar como root o con sudo:  sudo bash setup_vps.sh
# ══════════════════════════════════════════════════════════════════
set -e

# ── Configuración ────────────────────────────────────────────────
APP_USER="g3v3r"
APP_DIR="/home/${APP_USER}/cine-cadiz"
BACKEND_DIR="${APP_DIR}/backend"
VENV_DIR="${BACKEND_DIR}/venv"
SERVICE_FILE="/etc/systemd/system/cinecadiz.service"
LOG_DIR="/var/log/cinecadiz"

echo "════════════════════════════════════════"
echo "  CineCadiz — Setup VPS Ubuntu"
echo "════════════════════════════════════════"

# ── 1. Dependencias del sistema ──────────────────────────────────
echo "[1/6] Instalando dependencias del sistema..."
apt-get update -qq
apt-get install -y python3 python3-pip python3-venv python3-dev \
    build-essential libssl-dev libffi-dev git curl

# ── 2. Carpeta de logs ───────────────────────────────────────────
echo "[2/6] Creando directorio de logs..."
mkdir -p "${LOG_DIR}"
chown "${APP_USER}:${APP_USER}" "${LOG_DIR}"

# ── 3. Entorno virtual Python ────────────────────────────────────
echo "[3/6] Creando/actualizando virtualenv..."
sudo -u "${APP_USER}" python3 -m venv "${VENV_DIR}"
sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install --upgrade pip -q
sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" install -r "${BACKEND_DIR}/requirements.txt" -q
echo "      Paquetes instalados:"
sudo -u "${APP_USER}" "${VENV_DIR}/bin/pip" list --format=columns | grep -E "Flask|gunicorn|APScheduler|requests"

# ── 4. Fichero .env ──────────────────────────────────────────────
echo "[4/6] Configurando .env..."
if [ ! -f "${BACKEND_DIR}/.env" ]; then
    cp "${BACKEND_DIR}/.env.example" "${BACKEND_DIR}/.env"
    # Generar SECRET_KEY aleatoria automáticamente
    SECRET=$(sudo -u "${APP_USER}" "${VENV_DIR}/bin/python3" \
        -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s|cambia-esto-por-una-clave-secreta-segura|${SECRET}|g" \
        "${BACKEND_DIR}/.env"
    echo "      .env creado con SECRET_KEY generada."
    echo "      ⚠️  Edita ${BACKEND_DIR}/.env para cambiar ADMIN_PASSWORD."
else
    echo "      .env ya existe, no se sobreescribe."
fi
chown "${APP_USER}:${APP_USER}" "${BACKEND_DIR}/.env"
chmod 600 "${BACKEND_DIR}/.env"   # solo el usuario puede leerlo

# ── 5. Servicio systemd ──────────────────────────────────────────
echo "[5/6] Instalando servicio systemd..."
cp "${APP_DIR}/cinecadiz.service" "${SERVICE_FILE}"
systemctl daemon-reload
systemctl enable cinecadiz.service
systemctl restart cinecadiz.service

# Esperar un momento y comprobar estado
sleep 3
if systemctl is-active --quiet cinecadiz.service; then
    echo "      ✅ Servicio arrancado correctamente."
else
    echo "      ❌ El servicio no arrancó. Revisa los logs:"
    echo "         journalctl -u cinecadiz -n 50"
    systemctl status cinecadiz.service --no-pager
fi

# ── 6. Resumen ───────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════"
echo "  Instalación completada"
echo "════════════════════════════════════════"
echo ""
echo "  App accesible en:  http://57.129.126.202"
echo "  Logs de acceso:    ${LOG_DIR}/access.log"
echo "  Logs de errores:   ${LOG_DIR}/error.log"
echo "  Logs del sistema:  journalctl -u cinecadiz -f"
echo ""
echo "  Comandos útiles:"
echo "    sudo systemctl status  cinecadiz   # estado"
echo "    sudo systemctl restart cinecadiz   # reiniciar"
echo "    sudo systemctl stop    cinecadiz   # parar"
echo "    sudo journalctl -u cinecadiz -f    # logs en tiempo real"
echo ""
echo "  Para actualizar el código:"
echo "    cd ${APP_DIR} && git pull"
echo "    sudo systemctl restart cinecadiz"
echo ""
