# run_bot.py
import time
import requests
import logging

logging.basicConfig(level=logging.INFO)

def start_bot():
    url = "http://127.0.0.1:8000/run-cycle"
    print("🚀 Bot iniciado. Ejecutando ciclo cada 5 minutos...")
    
    while True:
        try:
            response = requests.post(url)
            print(f"Iteración completada: {response.json()}")
        except Exception as e:
            print(f"Error en el ciclo: {e}")
        
        # Esperar 5 minutos (300 segundos)
        time.sleep(300)

if __name__ == "__main__":
    start_bot()