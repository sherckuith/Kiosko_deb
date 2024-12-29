import os
import json
import time
import threading
import asyncio
import logging
import glob
import websockets
from datetime import datetime
import hashlib
from PIL import Image, ImageDraw, ImageFont
from flask import Flask, render_template, send_from_directory, make_response, jsonify, request
from flask_socketio import SocketIO
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from escpos.printer import Usb
import shutil
import socket
import barcode
from barcode.writer import ImageWriter




class TorreConsulta:
    def __init__(self):
        self.last_ws_response = None
        self.rfid_code = None
        self.image_data = None
        self.observer = None
        self.config_data = None
        self.ip = None
        self.port_server = None
        self.port_app = None
        self.host_server = None
        self.ws_url = None
        self.ws_data = None
        self.presentation_time = None
        self.temp_image_time = None
        self.font_type = None
        self.base_dir = None
        self.imagenes_dir = None
        self.temp_dir = None
        self.font_path = None
        self.image_source = None
        self.config_archive = 'config.cfg'
        self.lock_file = 'lock'
        
        self.setup_directories()
        
        if self.is_port_in_use(self.port_server):
            print(f"Error: El puerto {self.port_server} está en uso. Por favor, selecciona otro puerto.")
            exit(1)

        self.app = Flask(__name__, template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'))  # Explicit template folder
        self.socketio = SocketIO(self.app)

        if self.is_port_in_use(self.port_server) == False:
            print('\n')
            print(f"********  Aplicacion web desplegada en el puerto {self.port_server}  ********")
            print('\n')
        else:
            print(f"Error al iniciar Flask: El puerto {self.port_server} está en uso. Por favor, selecciona otro puerto.")
            exit(1)
        
        self.print_config()
        self.setup_routes()
        self.setup_file_monitor()

        # Start background tasks
        rfid_thread = threading.Thread(target=self.read_hid_device_loop, daemon=True)
        rfid_thread.start()
        # print("Hilo de lectura RFID iniciado.") # Debug
        flask_thread = threading.Thread(target=self.run_flask, daemon=True)
        flask_thread.start()
        # print("Hilo de Flask iniciado.") # Debug
        self.eliminar_contenido_temp()
        #self.generate_temp_image({}) # Generate a default temp image with WS
        #self.generate_image("Initial Image")
        #self.generar_imagen_prueba()



    def setup_directories(self):
        """Configura los directorios necesarios."""
        try:

            BASE_DIR=self.base_dir = os.path.dirname(os.path.abspath(__file__))
            print(f"Directorio base: {BASE_DIR}") # Debug
            
            self.config_archive_path = os.path.join(self.base_dir, self.config_archive)
            print(f"Ruta del archivo de configuración: {self.config_archive_path}") # Debug

            if self.load_config_from_file(self.config_archive_path):
                print("Configuración cargada correctamente.")

            else:
                print("Error al cargar la configuración.")
                exit(1)

            
            self.imagenes_dir = os.path.join(self.base_dir, self.config_data.get('route_image', 'Imagenes'))
            #self.imagenes_dir = os.path.join(self.base_dir, "Imagenes")
            print(f"Directorio de imágenes: {self.imagenes_dir}") # Debug
            self.temp_dir = os.path.join(self.base_dir, self.config_data.get('route_temp', 'Temp'))
            #self.temp_dir = os.path.join(self.base_dir, "Temp")
            print(f"Directorio temporal: {self.temp_dir}")    # Debug

            # Ruta de la fuente
            self.font_path = os.path.join(self.base_dir, self.config_data.get('route_font', 'Fonts') + self.font_type)
            #self.font_path = os.path.join(self.base_dir, 'Fonts',self.font_type)                print(f"Ruta de la fuente: {self.font_path}") # Debug
            
            # Crear directorios si no existen
            for directory in [self.imagenes_dir, self.temp_dir]:
                if not os.path.exists(directory):
                    os.makedirs(directory)
                    print(f"Directorio creado: {directory}")
            #print("Directorios configurados correctamente.") # Debug
        except Exception as e:
            print(f"Error al configurar directorios: {e}")

    def print_config(self):
        """Informa el estado de las variables globales."""
        """
        print("Cargarndo la configuración desde el archivo JSON") # Debug
        print("\n")
        print(f"Configuración cargada: {self.config_data}") # Debug
        print(f"Configuración cargada: {self.ip}") # Debug
        print(f"Configuración cargada: {self.port_server}") # Debug
        print(f"Configuración cargada: {self.port_app}") # Debug
        print(f"Configuración cargada: {self.host_server}") # Debug
        print(f"Configuración cargada: {self.ws_url}") # Debug
        print(f"Configuración cargada: {self.ws_data}") # Debug
        print(f"Configuración cargada: {self.presentation_time}") # Debug
        print(f"Configuración cargada: {self.temp_image_time}") # Debug
        print(f"Configuración cargada: {self.base_dir}") # Debug
        print(f"Configuración cargada: {self.imagenes_dir}") # Debug
        print(f"Configuración cargada: {self.temp_dir}") # Debug
        print(f"Configuración cargada: {self.font_path}") # Debug
        print("\n")
        """

    
    def load_config_from_file(self, config_path):
        """Carga y Configura las variables globales desde un archivo JSON."""
        try:
            with open(config_path, 'r') as config_file:
                self.config_data = json.load(config_file)
                print("\n") # Debug
                self.ip = self.config_data.get('ip', self.ip)
                print(f"IP: {self.ip}") # Debug
                self.port_server = self.config_data.get('port_server', self.port_server)
                print(f"Puerto de servidor: {self.port_server}") # Debug
                self.port_app = self.config_data.get('port_app', self.port_app)
                print(f"Puerto de aplicación: {self.port_app}") # Debug
                self.host_server = self.config_data.get('host_server', self.host_server)
                print(f"URL de clientes para consulta de datos: {self.host_server}") # Debug
                self.ws_url = f"ws://{self.ip}:{self.port_server}/{self.config_data.get('ws_path', 'torreconsulta1')}"
                print(f"URL de servidor WebSocket: {self.ws_url}") # Debug
                self.ws_data = self.config_data.get('ws_json', self.ws_data)
                print(f"Datos JSON para WebSocket: {self.ws_data}") # Debug
                self.presentation_time = self.config_data.get('presentation_time', self.presentation_time)
                print("Tiempo de presentación por imagen:", self.presentation_time) # Debug
                self.temp_image_time = self.config_data.get('temp_image_time', self.temp_image_time)
                print("Tiempo de presentacion de datos para imprimir:", self.temp_image_time) # Debug
                self.font_type = self.config_data.get('font_type', self.font_type)
                print("Tipo de fuente:", self.font_type)    # Debug
                self.image_source = self.config_data.get('name_image_temp', self.image_source)
                print("Nombre de la imagen temporal:", self.image_source) # Debug
                #print(f"Configuración cargada desde {config_path}") # Debug
                return True
        except Exception as e:
            print(f"Error al cargar la configuración desde {config_path}: {e}")
            return False
  
    def limpiar_codigo(self, code):
        """Limpia el código para que sea compatible con CODE39."""
        print(f"Limpiando código: {code}") # Debug
        return ''.join(filter(str.isalnum, code.upper()))

    def get_system_info(self):
        """Recopila información del sistema."""
        os_info = os.popen('cat /etc/os-release').read()
        kernel_info = os.popen('uname -a').read()
        cpu_info = os.popen("cat /proc/cpuinfo | grep 'model name' | uniq").read()
        memory_info = os.popen('free -h').read()
        disk_info = os.popen('df -h').read()
        ip_address = os.popen('hostname -I').read()
        firmware_version = os.popen('vcgencmd version').read()
        cpu_temp = os.popen('vcgencmd measure_temp').read()
        model_info = os.popen('cat /proc/device-tree/model').read()

        return {
            "os_info": os_info,
            "kernel_info": kernel_info,
            "cpu_info": cpu_info,
            "memory_info": memory_info,
            "disk_info": disk_info,
            "ip_address": ip_address,
            "firmware_version": firmware_version,
            "cpu_temp": cpu_temp,
            "model_info": model_info
        }
    
    def is_port_in_use(self, port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) == 0

    def generate_temp_image(self, data):
        """Genera una imagen temporal con los datos recibidos."""
        try:
            # Cargar la imagen base (IMAGEN_2.png)
            #self.imagenes_dir = os.path.join(self.base_dir, "Imagenes")
            #base_image_path = os.path.join(self.base_dir, self.config_data.get('route_image', 'Imagenes') + self.image_source)  # IMAGEN_2.png
            base_image_path = os.path.join(self.base_dir, self.image_source)  # IMAGEN_2.png
            print(f"Ruta de la imagen base: {base_image_path}") # Debug
            if not os.path.exists(base_image_path):
                print(f"Error: La imagen base {base_image_path} no existe.")
                return None
            img = Image.open(base_image_path).convert('RGB')
            draw = ImageDraw.Draw(img)

            # Cargar la fuente con tamaño 200
            try: #try .
                print(f"Intentando cargar fuente desde:{self.font_path}") # Debug
                font = ImageFont.truetype(self.font_path, size=250)  # Tamaño de fuente ajustado
                print(f"Fuente {font} cargada correctamente.")   # Debug
            except Exception as e:
                print(f"Error al cargar la fuente 'Monoton-Regular.ttf': {e}")
                font = ImageFont.load_default()
                #print(f"Fuente por defecto cargada: {font}")   # Debug
                # Fuente por defecto cargada: <PIL.ImageFont.FreeTypeFont object at 0x109a7c690>

            text = f"{data.get('puntostotal', 'N/A')}"

            # Centrar y dibujar texto
            lines = text.split('\n')
            img_width, img_height = img.size
            y_text = (img_height - len(lines) * (font.getbbox('A')[3] - font.getbbox('A')[1] + 140)) // 2  # Calcular posición vertical inicial

            for line in lines:
                text_bbox = draw.textbbox((0, 0), line, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                x_text = (img_width - text_width) // 2  # Centrar horizontalmente
                draw.text((x_text, y_text), line, font=font, fill='white')
                y_text += text_height + 20  # Ajustar posición vertical para la siguiente línea

            #Guardar la imagen con un timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_path = os.path.join(self.temp_dir, f"temp_{timestamp}.jpg")
            img.save(temp_path)
            #print(f"Imagen temporal: {temp_path}")

            # Emitir evento para mostrar la imagen temporal inmediatamente
            #####self.show_temp_image(temp_path)

            # Programar eliminación de la imagen temporal
            #threading.Timer(self.temp_image_time, self.eliminar_imagen, args=[temp_path]).start()
            # Programar eliminación forzada de todo el contenido TEMP
            threading.Timer(self.temp_image_time, self.eliminar_contenido_temp).start()

            # Confirmar que la imagen existe
            if os.path.exists(temp_path):
                return temp_path    # Retornar la ruta de la imagen generada
            else:
                print("Error: La imagen no se creó correctamente.")
                return None
        except Exception as e:
            print(f"Error al generar imagen temporal: {e}")
            return None

    def show_temp_image(self, temp_path):
        """Muestra la imagen temporal durante 20 segundos."""
        # Detener la presentación de imágenes
        #self.socketio.emit('show_temp_image', {'show': True})  # Emitir evento para mostrar la imagen temporal
        ####threading.Timer(20, self.reset_slideshow).start()  # Reiniciar la presentación después de 20 segundos
        #asyncio.run(self.delayed_message(3,"Esperando 3 segundos para mostrar la imagen temporal..."))
        #time.sleep(1)
        try:
            # Emitir el evento para el frontend
            self.socketio.emit('show_temp_image', {'path': temp_path})
            print(f"Mostrando imagen temporal: {temp_path}")
        except Exception as e:
            print(f"Error al mostrar la imagen temporal: {e}")


    def reset_slideshow(self):
        """Reinicia la presentación de imágenes."""
        self.socketio.emit('show_temp_image', {'show': False})  # Emitir evento para ocultar la imagen temporal
        #self.showSlides()  # Reiniciar la presentación de imágenes

    def setup_file_monitor(self):
        """Configura el monitor de archivos."""
        class ImageHandler(FileSystemEventHandler):
            def on_created(self, event):
                if not event.is_directory and event.src_path.endswith(('.jpg', '.jpeg', '.png')):
                    print(f"Nueva imagen detectada: {event.src_path}")

        try:
            event_handler = ImageHandler()
            self.observer = Observer()
            self.observer.schedule(event_handler, path=self.imagenes_dir, recursive=False)
            self.observer.start()
            #return observer
            # print(f"Monitoreando el directorio: {self.imagenes_dir}") # Debug
        except Exception as e:
            print(f"Error al configurar el monitor de archivos: {e}")


    def rotate_image(self, image_path, angle=90):
        """Rota una imagen y la guarda."""
        try:
            with Image.open(image_path) as img:
                rotated = img.rotate(angle, expand=True)
                rotated.save(image_path)
                print(f"Imagen rotada: {image_path}")
                return True
        except Exception as e:
            print(f"Error al rotar imagen: {e}")
            return False
        
    async def delayed_message(self,delay, message):
        print(f"Esperando {delay} segundos...")
        await asyncio.sleep(delay)
        print(message)
            
    async def ws_client(self, dato):
        """Maneja la comunicación con el WebSocket y garantiza la sincronización con la imagen generada."""
        #print(f"Enviando datos al servidor WebSocket...") # Debug
        self.ws_data['eventoid'] = dato  # Actualiza el eventoid con el ID del RFID
        print(f"Datos para WebSocket: {self.ws_data}") # Debug
        #print(f"\nEnviando a servidor ws://{self.ip}\nla estructura Json: {self.ws_data}\n")
        
        try:
            async with websockets.connect(self.ws_url) as websocket:
                await websocket.send(json.dumps(self.ws_data))
                print(f"Datos enviados por WebSocket: {self.ws_data}")
                # Esperar respuesta del WebSocket
                response = await asyncio.wait_for(websocket.recv(), timeout=5)
                print(f"Respuesta recibida de WebSocket: {response}")
                json.loads(response)
                # Procesar la respuesta
                self.last_ws_response = json.loads(response)
                print("\n")
                print("Respuesta del WebSocket:")
                print( "    eventoid: ", self.last_ws_response['eventoid'])
                print( "    puntostotal: ", self.last_ws_response['puntostotal'])
                print("\n")
                
                # Imprimir el código de barras
                if self.last_ws_response and 'puntostotal' in self.last_ws_response:
                    # print("Generando imagen temporal con datos válidos del WebSocket...") # Debug
                    
                    # Generar la imagen temporal
                    temp_path = self.generate_temp_image(self.last_ws_response)
                    #print(f"Imagen temporal generada: {temp_path}")
                    if temp_path and os.path.exists(temp_path):
                        # Agregar un breve retraso para asegurar que el archivo esté listo
                        await asyncio.sleep(0.5)

                        # Emitir evento para que el frontend muestre la imagen
                        self.socketio.emit('show_temp_image', {'path': temp_path}, namespace='/')
                        print(f"Imagen temporal lista y enviada al frontend: {temp_path}")
                    else:
                        print("Error al generar la imagen temporal, no se mostrará.")
                else:
                    print("Respuesta del WebSocket no válida o incompleta, no se generará imagen temporal.")
        except Exception as e:
            print(f"Error en la comunicación con WebSocket: {e}")


    def print_barcode(self, eventoid, puntostotal):
        try:
            datos_sucios = f"{eventoid}{puntostotal}"
            #print(f"Datos sucios para codificar con hash y hacer el código de barras: {datos_sucios}")
            identificador = hashlib.sha256(datos_sucios.encode()).hexdigest()[:8]
            #print(f"Identificador sucio creado por hash: {identificador}")
            datos_limpios = self.limpiar_codigo(f"{identificador}") # limpia el código para que sea compatible con CODE39
            #print(f"Datos Limpios para el código de barras: {datos_limpios}")
            print(f"Código de barras: {datos_limpios}")

            try:
                #conectando a impresora
                printer = Usb(0x04b8, 0x0e28)  # Vendor ID y Product ID de Epson TM-T20III
                # Imprimir encabezado y código de barras
                printer.text("\n***** Joy Challenge *****\n\n")
                printer.text("Comprobante para canjear\npuntos acumulados.\n")
                #printer.text(f"ID Cliente: {identificador}\n")
                printer.text(f"Brasalete ID: {eventoid}\n")
                printer.text(f"Puntos: {puntostotal}\n\n")
                printer.barcode(datos_limpios, 'CODE39', width=3, height=200, font='B')
                # Código base de 12 dígitos (sin el dígito de control)
                #codigo_ean = f"12345678{puntostotal}"
                #print(f"Código EAN13: {codigo_ean}")
                # Configuración del escritor para generar una imagen PNG
                #writer = ImageWriter()# Crear el objeto EAN13 con el código
                #ean13 = barcode.get('ean13', codigo_ean, writer=writer)
                # Guardar el código de barras como archivo PNG
                #filename = ean13.save("codigo_ean13")
                #print(f"Código de barras guardado como {filename}.png")
                # Cargar la imagen generada
                #imagen = Image.open("codigo_ean13.png")
                #imagen.show()

                #printer.barcode(codigo_ean, 'EAN13', width=2, height=100, font='A')
                #printer.barcode(datos_limpios, 'JAN', width=2, height=100, font='A')
                printer.text("\n\n")
                printer.cut()

                print("Código de barras impreso correctamente.")
                return True
            except Exception as e:
                print(f"Error al conectar con impresora: {e}\n")
                return False

        except Exception as e:
            print(f"Error al generar datos para el código de barras: {e}\n")
            return False
        
    """
    def generate_image(self, text):
        #Genera una imagen con el texto proporcionado.
        try:
            print(f"Generando imagen con texto: {text}")
            img = Image.new('RGB', (1280, 720), (0, 0, 0))
            d = ImageDraw.Draw(img)

            try:
                font = ImageFont.truetype(self.font_path, size=160)
                print("Fuente 'Monoton-Regular.ttf' cargada correctamente.")
            except Exception as e:
                print(f"Error al cargar la fuente 'Monoton-Regular.ttf': {e}")
                font = ImageFont.load_default()
                print("Fuente por defecto cargada.")

            font_size = 160
            text_bbox = d.textbbox((0, 0), text, font=font, font_size=font_size)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            x = (1280 - text_width) / 2
            y = (720 - text_height) / 2
            d.text((x, y), text, font=font, fill=(255, 255, 255), font_size=font_size)

            timestamp = int(time.time() * 1000)  # Timestamp en milisegundos
            img_name = f"{timestamp}.jpg"
            img_path = os.path.join(self.temp_dir, img_name)
            img.save(img_path)
            print(f"Imagen guardada como: {img_path}")
            return img_path, timestamp

        except Exception as e:
            print(f"Error al generar imagen: {e}")
            #return None, None
            return img_path, timestamp
        """
    def encontrar_dispositivo_hid(self):
        """Busca y devuelve el primer dispositivo HID disponible."""
        try:
            dispositivos = glob.glob("/dev/hidraw*")
            if not dispositivos:
                #print("No se encontraron dispositivos HID.")
                #print(".") # Debug
                return None
            print(f"Dispositivo HID encontrado: {dispositivos[0]}")
            return dispositivos[0]  # Devuelve el primer dispositivo disponible
        except Exception as e:
            print(f"Error al buscar dispositivos HID: {e}")
            return None

    def read_hid_device_loop(self):
        """Lee datos del dispositivo HID de forma continua."""
        while True:
            dispositivo = self.encontrar_dispositivo_hid()
            if not dispositivo:
                time.sleep(2)  # Esperar antes de volver a buscar
                continue

            try:
                with open(dispositivo, 'rb') as f:
                    print(f"Leyendo datos del dispositivo HID: {dispositivo}")
                    hex_trama = []
                    while True:
                        data = f.read(8)
                        if data:
                            relevant_data = [byte for byte in data if byte != 0]
                            if relevant_data:
                                hex_trama.extend(f"{byte:02x}" for byte in relevant_data)
                                if len("".join(hex_trama)) >= 22:
                                    self.procesar_trama("".join(hex_trama))
                                    hex_trama = []
                                    print(f"RFID Code: {self.rfid_code}")
                        else:
                            # Manejar el caso donde no se leen datos (posible desconexión)
                            print("No se leyeron datos del dispositivo HID. Reiniciando lectura...")
                            break  # Salir del bucle interno para volver a buscar el dispositivo
            except FileNotFoundError:
                print("Dispositivo desconectado. Buscando nuevamente...")
                time.sleep(2)
            except Exception as e:
                print(f"Error al leer el dispositivo HID: {e}")
                time.sleep(2)
                #dispositivo = self.encontrar_dispositivo_hid()

    def procesar_trama(self, trama):
        """Procesa la trama recibida del dispositivo HID."""
        try:
            #print(f"Procesar ID: {trama}") # Debug
            if trama:
                self.rfid_code = trama  # Guarda el código RFID
                print(f"ID del RFID: {self.rfid_code}")
                asyncio.run(self.ws_client(self.rfid_code))  # Envía el ID del RFID al servidor
                # Aquí puedes generar la imagen temporal si es necesario, pero se hace en ws_client
                #img_path, timestamp = self.generate_image(trama)
                #threading.Timer(20.0, self.eliminar_imagen, args=[self.ruta_imagen_new]).start()
            print("Trama procesada.")
        except Exception as e:
            print(f"Error al procesar la trama: {e}")
   
    def eliminar_contenido_temp(self):
        """Elimina todos los archivos y carpetas en el directorio temporal (TEMP)."""
        try:
            for filename in os.listdir(self.temp_dir):
                file_path = os.path.join(self.temp_dir, filename)
                #print(f"Eliminando: {file_path}")
                if os.path.isfile(file_path): #Si es un archivo, se elimina y se imprime un mensaje confirmando su eliminación
                    os.remove(file_path)
                    #print(f"Archivo eliminado: {file_path}")
                elif os.path.isdir(file_path): #Si el elemento es un directorio, se elimina recursivamente
                    shutil.rmtree(file_path)
                    #print(f"Carpeta eliminada: {file_path}")
                print("TEMP eliminado.")
        except Exception as e:
            print(f"Error al limpiar el directorio TEMP: {e}")
    
    def eliminar_imagen(self, img_path):
        """Elimina una imagen."""
        try:
            if os.path.exists(img_path):
                os.remove(img_path)
                print(f"Imagen eliminada: {img_path}")
            else:
                print(f"La imagen no existe: {img_path}")
        except Exception as e:
            print(f"Error al eliminar la imagen: {e}")

    # Crear imagen de prueba solo para saber si esta creando bien las imagenes
    def generar_imagen_prueba(self):
        """Genera una imagen de prueba."""
        try:
            print("Generando imagen de prueba...")
            if not os.path.exists(self.ruta_imagen_new):
                print("Imagen base no encontrada. Creando una imagen simple...")
                imagen = Image.new("RGB", (1280, 720), (0, 0, 0))  # Fondo negro
                imagen.save(self.ruta_imagen_new)
            else:
                imagen = Image.open(self.ruta_imagen_new).convert("RGB")

            # Crear archivo de bloqueo
            with open(self.lock_file, "w") as lock:
                lock.write("locked")

            # Preparar fuente
            try:
                font = ImageFont.truetype(self.font_path, size=60)
            except:
                font = ImageFont.load_default()

            # Crear dibujo
            draw = ImageDraw.Draw(imagen)
            ancho, alto = imagen.size

            # Datos de prueba o texto del servidor
            texto_prueba = "Excelente Juego\n\nHas alcanzado\n\n10000 puntos,\n\nSigue Jugando"
            lineas = texto_prueba.split("\n")
            # Configuración del texto y fondo
            y_inicio = (alto - len(lineas) * 60) // 2  # Centramos verticalmente
            color_texto = (255, 255, 255)  # Blanco
            color_fondo_texto = (0, 0, 0)  # Negro

            for i, linea in enumerate(lineas):
                text_bbox = draw.textbbox((0, 0), linea, font=font)
                ancho_texto = text_bbox[2] - text_bbox[0]
                alto_texto = text_bbox[3] - text_bbox[1]
                x = (ancho - ancho_texto) / 2
                y = y_inicio + i * (alto_texto + 10)
                draw.rectangle(
                    [x - 10, y - 10, x + ancho_texto + 10, y + alto_texto + 10],
                    fill=color_fondo_texto
                )
                draw.text((x, y), linea, font=font, fill=color_texto)

            # Guardar la imagen generada
            fecha_hora = datetime.now().strftime("%H%M%S%d%m%Y")
            nombre_imagen = f"temp_{fecha_hora}.jpg"
            ruta_imagen = os.path.join(self.temp_dir, nombre_imagen)
            imagen.save(ruta_imagen)
            print(f"Imagen generada: {ruta_imagen}")

            # Eliminar archivo de bloqueo
            if os.path.exists(self.lock_file):
                os.remove(self.lock_file)

        except Exception as e:
            print(f"Error al generar la imagen de prueba: {e}")
    
    def run_flask(self):
        logging.basicConfig(level=logging.DEBUG)  # Configura el nivel de registro
        log = logging.getLogger(__name__)
        try:
            log.info("Iniciando la aplicación Flask...")
            self.socketio.run(self.app, host=self.host_server, port=self.port_app, debug=False)
            log.info("Aplicación Flask iniciada correctamente.") # Mensaje si el inicio es exitoso
        except Exception as e:
            log.error(f"Error al iniciar la aplicación Flask: {e}")

    ##############################################################################################################################
                ########################################### Rutas HTTP/WS ################################################
    ##############################################################################################################################

    def setup_routes(self):
        """Configura las rutas de Flask."""

        # Ruta principal para servir la página HTML del kiosko
        @self.app.route('/')
        def index():
            """Página principal."""
            images = sorted([f for f in os.listdir(self.imagenes_dir) if f.endswith(('.jpg', '.jpeg', '.png'))])
            temp_images = sorted([f for f in os.listdir(self.temp_dir) if f.endswith(('.jpg', '.jpeg', '.png'))])
            timestamp = int(time.time() * 1000)  # Timestamp en milisegundos
            #print(f"Imágenes encontradas: {images}")  # Debug
            #print(f"Imágenes temporales encontradas: {temp_images}")  # Debug
            print("Recargando pagina...")
            try:
                return render_template('index.html',
                                 temp_imagenes=temp_images,
                                 imagenes=images,
                                 timestamp=timestamp,
                                 temp_image_time=self.temp_image_time) # Pass temp_image_time
                
            except Exception as e:
                return f"Error al listar imágenes: {e}", 500

       # Ruta para mostrar la información del sistema
        @self.app.route('/system_info')
        def system_info():
            print("Mostrando la información del sistema VOLTA\n")
            info = self.get_system_info()
            return render_template('system_info.html', info=info)
        
        @self.app.route('/imagenes/<filename>')
        def serve_image(filename):
            print(f"Mostrando imagen solicitada por http: {filename}")
            response = make_response(send_from_directory(self.imagenes_dir, filename))
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            return response

        @self.app.route('/temp_imagenes/<filename>')
        def serve_temp_image(filename):
            print(f"Mostrando imagen temporal solicitada por http: {filename}")
            response = make_response(send_from_directory(self.temp_dir, filename))
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            return response

        @self.app.route('/rotate/<filename>', methods=['POST'])
        def rotate_image_endpoint(filename):
            print(f"Rotando imagen (orden solicitada por http): {filename}")
            try:
                angle = int(request.args.get('angle', 90))
                image_path = os.path.join(self.imagenes_dir, filename)
                if self.rotate_image(image_path, angle):
                    return jsonify({"success": True})
                return jsonify({"success": False, "error": "Failed to rotate image"})
            except Exception as e:
                return jsonify({"success": False, "error": str(e)})

        @self.app.route('/set_presentation_time', methods=['POST'])
        def set_presentation_time():
            print("Estableciendo tiempo de presentación desde http...")
            try:
                time_ms = int(request.json.get('time_ms', 5000))
                self.presentation_time = time_ms
                return jsonify({"success": True, "presentation_time": time_ms})
            except Exception as e:
                return jsonify({"success": False, "error": str(e)})

        @self.app.route('/simulate_rfid', methods=['POST'])
        def simulate_rfid():
            print("\nSimulando lectura RFID desde http...\n")
            try:
                data = request.json
                print(f"\nDatos simulados: {data}")
                # Primero consultar el evento al servidor
                eventoid = data.get('eventoid')
                self.procesar_trama(eventoid)
                #response_data = asyncio.run(consultar_evento(eventoid))
                #if response_data:
                #    self.generate_temp_image(response_data)  # Generar imagen temporal con la respuesta
                #    return jsonify({"success": True})
                #return jsonify({"success": False, "error": "Failed to generate image"})
                return jsonify({"success": eventoid})
            except Exception as e:
                return jsonify({"success": False, "error": str(e)})

        async def consultar_evento(eventoid):
            print(f"Consultando evento por WebSocket: {eventoid}")
            uri = self.ws_url
            request_data = {"comando": "checkpoints", "eventoid": eventoid}

            try:
                async with websockets.connect(uri) as websocket:
                    await websocket.send(json.dumps(request_data))
                    response = await websocket.recv()
                    print(f"Respuesta del servidor por WebSocket: {response}")  # Debug
                    return json.loads(response)
            except Exception as e:
                print(f"Error en la conexión WebSocket: {e}")
                return {"error": str(e)}

        # Ruta para probar una impresión desde un JSON
        @self.app.route("/check_printer", methods=["POST"])
        def check_printer():
            print("\nPrueba la impresión desde un JSON.")
            try:
                data = request.json
                #print(f"Datos recibidos desde @self.app.route(/check_printer): {data}") # Debug
                if data.get('eventoid') and data.get('puntostotal'):
                    print(f"Imprimiendo código de barras: {data}")
                    success = self.print_barcode(data['eventoid'], data['puntostotal'])
                    return jsonify({"success": success})
                return jsonify({"success": False, "error": "Datos insuficientes"})
            except Exception as e:
                return jsonify({"success": False, "error": str(e)})

        # Ruta para imprimir el código de barras en la impresora Epson TM-T20III.
        @self.app.route('/printer', methods=['POST'])
        def print_code():
            print(f"\n\n\n#######  Datos recibidos  ########\n")
            try:
                print(f"last_ws_response: {self.last_ws_response}")
                if self.last_ws_response:
                    success = self.print_barcode(
                        self.last_ws_response['eventoid'],
                        self.last_ws_response['puntostotal']
                    )
                    print(f"success => self.print_barcode: {success}")
                    return jsonify({"success": success})
                print("No hay datos disponibles")
                return jsonify({"success": False, "error": "No hay datos disponibles"})
            except Exception as e:
                print(f"Error en la ruta /printer: {e}")  # Log del error
                return jsonify({"success": False, "error": str(e)})

        # Simula la impresión de un código de barras y la creación de la imagen.
        @self.app.route('/test',methods=['POST'])
        def test_print():
            data = request.json
            print(f"Datos recibidos desde @app.route(/test): {data}")
            # Generar imagen temporal
            self.generate_temp_image(data)
            print(f"Generando imagen temporal por test http POST: {data}")

            # Imprimir código de barras
            if data.get('eventoid') and data.get('puntostotal'):
                print(f"Imprimiendo código de barras: {data}")
                success = self.print_barcode(data['eventoid'], data['puntostotal'])
                return jsonify({"success": success})
            return jsonify({"success": False, "error": "No data provided"})

        # Ruta para manejar solicitudes RFID
        @self.app.route("/rfid", methods=["POST"])
        async def rfid():
            data = request.json
            eventoid = data.get('eventoid'),
            puntostotal = data.get('puntostotal')
            print(f"Datos recibidos desde @app.route(/rfid): {data}")

if __name__ == '__main__':
    torre = TorreConsulta()
    # Iniciar el servidor Flask en el hilo principal
    torre.run_flask()
