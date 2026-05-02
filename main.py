from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
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

client = Groq(api_key="TU_API_KEY_DE_GROQ")

ultima_pantalla = ""
historial_pantallas = []

async def capturar_pantalla(page):
    screenshot = await page.screenshot(type="jpeg", quality=60)
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

escribir_campo SELECTOR:::TEXTO
click en TEXTO_DEL_BOTON
navegar a URL
tarea completada RESULTADO

EJEMPLOS para login:
escribir_campo input[name='usuario']:::miusuario
escribir_campo input[name='password']:::mipassword
escribir_campo input[type='text']:::miusuario
escribir_campo input[type='password']:::mipassword
click en Entrar
tarea completada Login realizado correctamente

IMPORTANTE:
- Para rellenar campos de login usa escribir_campo con el selector CSS y el texto separados por :::
- Si ves que ya estás logueado o dentro del sistema responde con tarea completada
- Si ves un mensaje de error de login responde con tarea completada ERROR de login

¿Qué acción hacer?"""
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
            max_tokens=80
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

@app.get("/pantalla", response_class=HTMLResponse)
def ver_pantalla():
    global ultima_pantalla, historial_pantallas
    if not ultima_pantalla:
        return "<h2>No hay pantalla guardada todavía</h2>"
    
    html = """
    <html>
    <head>
        <title>Pantallas del agente</title>
        <style>
            body { font-family: Arial; background: #1a1a1a; color: white; padding: 20px; }
            h2 { color: #4CAF50; }
            .pantalla { margin: 20px 0; border: 2px solid #4CAF50; padding: 10px; border-radius: 8px; }
            .pantalla h3 { color: #aaa; font-size: 14px; }
            img { max-width: 100%; border-radius: 4px; }
            .ultima { border-color: #ff9800; }
        </style>
    </head>
    <body>
        <h2>Historial de pantallas del agente</h2>
    """
    
    for i, (accion, img) in enumerate(historial_pantallas):
        clase = "ultima" if i == len(historial_pantallas) - 1 else ""
        html += f"""
        <div class='pantalla {clase}'>
            <h3>Paso {i+1}: {accion}</h3>
            <img src='data:image/jpeg;base64,{img}'/>
        </div>
        """
    
    html += "</body></html>"
    return html

@app.post("/ejecutar")
async def ejecutar_tarea(request: Request):
    global ultima_pantalla, historial_pantallas
    historial_pantallas = []

    datos = await request.json()
    tarea = datos.get("tarea")
    url_inicio = datos.get("url", "https://www.google.com")
    usuario = datos.get("usuario", "")
    password = datos.get("password", "")

    if usuario and password:
        tarea = f"{tarea}. Usuario: '{usuario}', Contraseña: '{password}'"

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
        await pagina.wait_for_load_state("domcontentloaded")
        await pagina.wait_for_timeout(3000)

        pasos = []

        for intento in range(15):
            print(f"--- Intento {intento + 1} ---", flush=True)

            pantalla = await capturar_pantalla(pagina)
            ultima_pantalla = pantalla

            accion = await preguntarle_a_groq(tarea, pantalla)
            print(f"Acción: {accion}", flush=True)
            pasos.append(accion)

            historial_pantallas.append((accion, pantalla))

            if "tarea completada" in accion.lower() or "error" in accion.lower():
                break

            elif accion.lower().startswith("escribir_campo"):
                try:
                    contenido = accion.replace("escribir_campo", "").strip()
                    partes = contenido.split(":::")
                    selector = partes[0].strip()
                    texto = partes[1].strip() if len(partes) > 1 else ""
                    campo = await pagina.wait_for_selector(selector, timeout=5000)
                    await campo.click()
                    await campo.fill("")
                    await campo.type(texto, delay=50)
                    print(f"Escrito '{texto}' en '{selector}'", flush=True)
                    await pagina.wait_for_timeout(500)
                except Exception as e:
                    print(f"Fallo escribir_campo: {e}", flush=True)
                    try:
                        selector_generico = "input[type='text'], input[type='search'], input[name*='user'], input[name*='login']"
                        campo = await pagina.wait_for_selector(selector_generico, timeout=3000)
                        await campo.fill(texto)
                    except:
                        pass

            elif accion.lower().startswith("escribir"):
                texto_escribir = accion.lower().replace("escribir", "").strip()
                try:
                    selector = "input[type='text'], input[type='search'], textarea, [name='q'], [role='combobox'], [role='searchbox']"
                    campo = await pagina.wait_for_selector(selector, timeout=5000)
                    await campo.click()
                    await campo.fill("")
                    await campo.type(texto_escribir, delay=50)
                    await pagina.wait_for_timeout(500)
                    await campo.press("Enter")
                    print(f"Escrito: {texto_escribir}", flush=True)
                    await pagina.wait_for_load_state("domcontentloaded")
                    await pagina.wait_for_timeout(3000)
                except Exception as e:
                    print(f"Fallo al escribir: {e}", flush=True)

            elif accion.lower().startswith("click en"):
                texto = accion.lower().replace("click en", "").strip()
                try:
                    await pagina.get_by_text(texto, exact=False).first.click(timeout=5000)
                    await pagina.wait_for_load_state("domcontentloaded")
                    await pagina.wait_for_timeout(2000)
                    print(f"Click en: {texto}", flush=True)
                except:
                    try:
                        await pagina.locator(f"button:has-text('{texto}')").first.click(timeout=3000)
                    except:
                        try:
                            await pagina.locator(f"input[value*='{texto}']").first.click(timeout=3000)
                        except:
                            print(f"No se encontró el botón: {texto}", flush=True)

            elif accion.lower().startswith("navegar a"):
                url = accion.lower().replace("navegar a", "").strip()
                if not url.startswith("http"):
                    url = f"https://{url}"
                await pagina.goto(url)
                await pagina.wait_for_load_state("domcontentloaded")
                await pagina.wait_for_timeout(2000)

            await pagina.wait_for_timeout(1500)

        await navegador.close()

        return {
            "estado": "proceso terminado",
            "pasos": pasos,
            "ver_pantallas": "https://agente-ganera.onrender.com/pantalla"
        }
