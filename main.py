from fastapi import FastAPI, Request
from playwright.async_api import async_playwright
from groq import Groq
import base64

app = FastAPI(
    title="Agente IA",
    docs_url="/docs",
    openapi_url="/openapi.json" # Forzamos que se genere en esta ruta
)

# Añade este middleware para evitar problemas de CORS (muy común en Render)
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
client = Groq(api_key="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")

async def capturar_pantalla(page):
    screenshot = await page.screenshot()
    return base64.b64encode(screenshot).decode()

async def preguntarle_a_groq(tarea, pantalla_base64):
    respuesta = client.chat.completions.create(
        model="llama-3.2-90b-vision-preview",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"""Eres un agente que controla un navegador web.
Tu tarea es: {tarea}

Mira la pantalla y dime exactamente qué acción hacer ahora.
Responde SOLO con una de estas opciones:
- click en [texto exacto del botón o enlace]
- escribir [texto] en [nombre del campo]
- navegar a [url]
- tarea completada

Responde SOLO con la acción, nada más."""
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{pantalla_base64}"
                        }
                    }
                ]
            }
        ],
        max_tokens=100
    )
    return respuesta.choices[0].message.content.strip()

@app.get("/")
def root():
    return {"estado": "agente funcionando"}

@app.post("/ejecutar")
async def ejecutar_tarea(request: Request):
    print("1. Petición recibida")
    datos = await request.json()
    tarea = datos.get("tarea")
    url_inicio = datos.get("url", "https://www.google.com")

    async with async_playwright() as p:
        print("2. Iniciando Playwright...")
        navegador = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        print("3. Navegador abierto")
        pagina = await navegador.new_page()
        await pagina.goto(url_inicio)

        pasos = []

        for intento in range(20):
            pantalla = await capturar_pantalla(pagina)
            accion = await preguntarle_a_groq(tarea, pantalla)

            pasos.append(accion)

            if "tarea completada" in accion.lower():
                break
            elif accion.lower().startswith("click en"):
                texto = accion.replace("click en", "").replace("Click en", "").strip()
                try:
                    await pagina.get_by_text(texto, exact=False).click()
                except:
                    pass
            elif accion.lower().startswith("escribir"):
                partes = accion.split(" en ")
                texto = partes[0].replace("escribir", "").replace("Escribir", "").strip()
                campo = partes[1].strip() if len(partes) > 1 else ""
                try:
                    await pagina.fill(f"[placeholder*='{campo}']", texto)
                except:
                    pass
            elif accion.lower().startswith("navegar a"):
                url = accion.replace("navegar a", "").replace("Navegar a", "").strip()
                await pagina.goto(url)

            await pagina.wait_for_timeout(2000)

        await navegador.close()

        return {
            "estado": "completado",
            "pasos": pasos
        }
