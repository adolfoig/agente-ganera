from fastapi import FastAPI, Request
from playwright.async_api import async_playwright
from groq import Groq
import base64

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

client = Groq(api_key="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")

async def capturar_pantalla(page):
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
Tarea: {tarea}

REGLAS ESTRICTAS:
- Responde SOLO con UNA línea
- Sin explicaciones, sin puntos, sin comillas
- Usa EXACTAMENTE uno de estos formatos:

escribir TEXTO_A_ESCRIBIR
click en TEXTO_DEL_BOTON
navegar a URL
tarea completada RESULTADO

Ejemplos correctos:
escribir precio bitcoin
click en Buscar
navegar a https://duckduckgo.com
tarea completada El precio es 94000 USD

IMPORTANTE: Si ya ves resultados de búsqueda en pantalla, responde con tarea completada y el resultado que ves. No sigas buscando si ya hay resultados visibles.

¿Qué ves en pantalla y qué acción hay que hacer?"""
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
            max_tokens=50
        )
        respuesta_texto = respuesta.choices[0].message.content.strip()
        primera_linea = respuesta_texto.split('\n')[0].strip()
        return primera_linea
    except Exception as e:
        print(f"Error en Groq: {e}", flush=True)
        return "error"

@app.get("/")
def root():
    return {"estado": "agente funcionando"}

@app.post("/ejecutar")
async def ejecutar_tarea(request: Request):
    datos = await request.json()
    tarea = datos.get("tarea")
    url_inicio = datos.get("url", "https://duckduckgo.com")

    async with async_playwright() as p:
        navegador = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--single-process",
                "--disable-blink-features=AutomationControlled"
            ]
        )

        contexto = await navegador.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            java_script_enabled=True,
            locale="es-ES",
            timezone_id="Europe/Madrid"
        )

        await contexto.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
            Object.defineProperty(navigator, 'languages', { get: () => ['es-ES', 'es'] });
            window.chrome = { runtime: {} };
        """)

        pagina = await contexto.new_page()
        await pagina.goto(url_inicio)
        await pagina.wait_for_load_state("networkidle")
        await pagina.wait_for_timeout(2000)

        pasos = []
        ya_busco = False

        for intento in range(15):
            print(f"--- Intento {intento + 1} ---", flush=True)

            pantalla = await capturar_pantalla(pagina)
            accion = await preguntarle_a_groq(tarea, pantalla)

            print(f"Acción: {accion}", flush=True)
            pasos.append(accion)

            if "tarea completada" in accion.lower() or "error" in accion.lower():
                break

            elif accion.lower().startswith("escribir") and not ya_busco:
                texto_escribir = accion.lower().replace("escribir", "").strip()
                try:
                    selector = "input[type='text'], input[type='search'], textarea, [name='q'], [role='combobox'], [role='searchbox']"
                    campo = await pagina.wait_for_selector(selector, timeout=5000)
                    await campo.click()
                    await campo.fill("")
                    await campo.type(texto_escribir, delay=50)
                    await pagina.wait_for_timeout(500)
                    await campo.press("Enter")
                    print(f"Escrito y buscado: {texto_escribir}", flush=True)
                    ya_busco = True
                    # Esperar a que carguen los resultados
                    await pagina.wait_for_load_state("networkidle")
                    await pagina.wait_for_timeout(3000)
                except Exception as e:
                    print(f"Fallo al escribir: {e}", flush=True)

            elif accion.lower().startswith("escribir") and ya_busco:
                print("Ya se realizó la búsqueda, esperando resultados...", flush=True)
                await pagina.wait_for_timeout(2000)

            elif accion.lower().startswith("click en"):
                texto = accion.lower().replace("click en", "").strip()
                try:
                    await pagina.get_by_text(texto, exact=False).first.click(timeout=5000)
                    await pagina.wait_for_load_state("networkidle")
                    await pagina.wait_for_timeout(2000)
                except:
                    try:
                        await pagina.locator(f"[aria-label*='{texto}']").first.click(timeout=3000)
                    except:
                        pass

            elif accion.lower().startswith("navegar a"):
                url = accion.lower().replace("navegar a", "").strip()
                if not url.startswith("http"):
                    url = f"https://{url}"
                await pagina.goto(url)
                await pagina.wait_for_load_state("networkidle")
                await pagina.wait_for_timeout(2000)

            await pagina.wait_for_timeout(2000)

        await navegador.close()

        return {
            "estado": "proceso terminado",
            "pasos": pasos
        }
