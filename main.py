from fastapi import FastAPI, Request
from playwright.async_api import async_playwright
from groq import Groq
import base64
import os

app = FastAPI(
    title="Agente IA",
    docs_url="/docs",
    openapi_url="/openapi.json"
)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# RECOMENDACIÓN: Usa os.environ.get("GROQ_API_KEY") en Render Settings por seguridad
client = Groq(api_key="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")

async def capturar_pantalla(page):
    # Optimizamos la captura para que no pese tanto
    screenshot = await page.screenshot(type="jpeg", quality=50)
    return base64.b64encode(screenshot).decode()

async def preguntarle_a_groq(tarea, pantalla_base64):
    try:
        respuesta = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"""Eres un agente que controla un navegador web.
Tarea actual: {tarea}

Instrucciones de respuesta:
1. Si aún necesitas navegar, responde SOLO con: click en [texto], escribir [texto] en [campo], o navegar a [url].
2. Si ya ves la información solicitada en la pantalla (como el precio), responde: 'La información es [dato encontrado], tarea completada'.

Mira la pantalla y dime la acción o respuesta final:"""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{pantalla_base64}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=100
        )
        return respuesta.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error en Groq: {e}", flush=True)
        return "Error"

@app.get("/")
def root():
    return {"estado": "agente funcionando"}

@app.post("/ejecutar")
async def ejecutar_tarea(request: Request):
    print("1. Petición recibida", flush=True)
    datos = await request.json()
    tarea = datos.get("tarea")
    url_inicio = datos.get("url", "https://www.google.com")

    async with async_playwright() as p:
        print("2. Iniciando Playwright...", flush=True)
        navegador = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--single-process"
            ]
        )
        
        print("3. Navegador abierto", flush=True)
        contexto = await navegador.new_context(viewport={'width': 1280, 'height': 720})
        pagina = await contexto.new_page()
        await pagina.goto(url_inicio)

        pasos = []

        # Reducimos a 10 pasos para evitar timeouts excesivos en Render
        for intento in range(10):
            print(f"--- Intento {intento + 1} ---", flush=True)
            pantalla = await capturar_pantalla(pagina)
            accion = await preguntarle_a_groq(tarea, pantalla)
            
            print(f"Acción decidida: {accion}", flush=True)
            pasos.append(accion)

            if "tarea completada" in accion.lower() or "error" in accion.lower():
                break
            
            elif "click en" in accion.lower():
                texto = accion.lower().replace("click en", "").strip()
                try:
                    # Intento de click más robusto
                    await pagina.get_by_text(texto, exact=False).click(timeout=5000)
                except:
                    pass
            
            elif "escribir" in accion.lower():
                partes = accion.lower().split(" en ")
                texto_escribir = partes[0].replace("escribir", "").strip()
                
                try:
                    # Selector universal para barras de búsqueda (Google y otros)
                    selector = "textarea, input[type='text'], input[type='search'], [role='combobox']"
                    campo = await pagina.wait_for_selector(selector, timeout=5000)
                    await campo.fill(texto_escribir)
                    await campo.press("Enter") # <-- ESTO HACE QUE LA BÚSQUEDA SE EJECUTE
                    print(f"Texto '{texto_escribir}' enviado con Enter", flush=True)
                except Exception as e:
                    print(f"Fallo al escribir: {e}", flush=True)
            
            elif "navegar a" in accion.lower():
                url = accion.lower().replace("navegar a", "").strip()
                if not url.startswith("http"):
                    url = f"https://{url}"
                await pagina.goto(url)

            # Esperamos a que la página reaccione antes del siguiente ciclo
            await pagina.wait_for_timeout(3000)

        await navegador.close()
        print("Tarea finalizada.", flush=True)

        return {
            "estado": "proceso terminado",
            "pasos": pasos
        }
