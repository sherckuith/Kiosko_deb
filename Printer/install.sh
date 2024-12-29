#!/bin/bash

echo "====================================================="
echo "      Instalador de Impresoras EPSON, por Volta      "
echo "====================================================="
echo "                Desarrollado por:                    "
echo "   Ing. Ángel Yaguana, PhD(hc) y Ing. Fabián Ortiz   "
echo "                Datos de Contacto:                   "
echo " - Ángel: +593 99 652 6047 | Fabián: +593 99 833 8059"
echo " - Ciudad: Quito, Ecuador                            "
echo " - Correo: contact@volta.com                         "
echo "====================================================="
echo ""

# Variables importantes
TAR_FILE="./tmx-cups-src-ThermalReceipt-3.0.0.0.tar.gz"
PPD_PATH="./Thermal Receipt/ppd/tm-ba-thermal-rastertotmtr-180.ppd"
CURRENT_DIR=$(pwd)

# 1. Verificar que el archivo .tar.gz existe
if [ ! -f "$TAR_FILE" ]; then
  echo "No se encontró el archivo $TAR_FILE en $CURRENT_DIR. Por favor verifica la ruta."
  exit 1
fi

# 2. Actualizar sistema
echo "1. Actualizando el sistema..."
sudo apt update && sudo apt upgrade -y

# 3. Instalar dependencias necesarias
echo "2. Instalando dependencias necesarias..."
sudo apt install -y cmake libcups2-dev libcupsimage2-dev build-essential cups libusb-1.0-0 libusb-1.0-0-dev python3-pip

# 4. Instalar bibliotecas de Python necesarias
echo "3. Instalando bibliotecas de Python..."
pip install pyusb escpos --upgrade

# 5. Configurar permisos de USB
echo "4. Configurando permisos de USB..."
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="04b8", ATTR{idProduct}=="0e28", MODE="0666", GROUP="plugdev"' | sudo tee /etc/udev/rules.d/99-escpos.rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# 6. Agregar el usuario actual al grupo plugdev
echo "5. Agregando el usuario actual al grupo plugdev..."
sudo usermod -aG plugdev $USER
echo "Por favor, cierra sesión y vuelve a iniciar para que los cambios surtan efecto."

# 7. Extraer y compilar los drivers
echo "6. Extrayendo y compilando drivers..."
tar -xvzf "$TAR_FILE"
cd tmx-cups-src-ThermalReceipt-3.0.0.0
chmod +x build.sh install.sh
sudo ./build.sh
sudo ./install.sh
cd ..

# 8. Habilitar y asegurar CUPS
echo "7. Configurando y habilitando CUPS..."
sudo systemctl enable cups
sudo systemctl start cups

# 9. Configurar la impresora
echo "8. Configurando impresora en CUPS..."
DEVICE_URI=$(lpinfo -v | grep -i 'usb://EPSON' | awk '{print $2}')

if [ -z "$DEVICE_URI" ]; then
  echo "No se encontró una impresora EPSON conectada. Por favor verifica la conexión USB."
  exit 1
fi

if [ ! -f "$PPD_PATH" ]; then
  echo "El archivo PPD no se encontró en $PPD_PATH. Por favor verifica la instalación."
  exit 1
fi

sudo lpadmin -p TM-T20III -v "$DEVICE_URI" -P "$PPD_PATH" -E

# 10. Verificar configuración
echo "9. Verificando configuración de la impresora..."
lpstat -p

# 11. Prueba de impresión
echo "10. Realizando prueba de impresión..."
echo "Prueba de impresión desde la Epson TM-T20III" > test_print.txt
lpr -P TM-T20III -o media=RP80x2000 test_print.txt

echo "====================================================="
echo "Instalación completada con éxito. 🚀"
echo "Por favor, reinicia tu sesión para aplicar todos los cambios."
echo "====================================================="
