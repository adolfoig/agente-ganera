# Usamos la imagen oficial de Playwright que ya trae Python y los navegadores
FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

# Evita que Python genere archivos .pyc y permite ver los logs en tiempo real
ENV PYTHONUNBUFFERED=1

# Directorio de trabajo
WORKDIR /app

# Copiamos los requisitos primero para aprovechar la caché de Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalamos los binarios de Playwright (solo por seguridad, la imagen ya los trae)
# y las dependencias del sistema
RUN playwright install chromium

# Copiamos el resto del código
COPY . .

# Comando para arrancar la app (ajusta main:app al nombre de tu archivo)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
