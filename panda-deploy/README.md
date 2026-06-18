# 🐼 PANDA — Radar de Oportunidades Estratégicas

**Universidad del Rosario** — ECH + FEIPU

Agente IA que escanea fuentes nacionales e internacionales y empareja convocatorias vigentes con el perfil real de investigadores, grupos y observatorios de la URosario.

## 📁 Estructura

```
├── web/
│   └── index.html          ← La aplicación PANDA (GitHub Pages)
├── proxy/
│   ├── panda_proxy.py      ← Proxy seguro (Render.com)
│   └── requirements.txt    ← Dependencias Python
├── render.yaml             ← Configuración de despliegue Render
├── .gitignore
└── README.md
```

## 🔒 Seguridad

El proxy implementa 5 capas de seguridad:

1. **CORS restringido** — Solo acepta peticiones desde tu dominio de GitHub Pages
2. **Token secreto** — Header `X-Panda-Token` validado en cada petición
3. **Rate limiting** — Máximo 15 peticiones por minuto por IP
4. **Whitelist de modelos** — Solo Haiku, Sonnet y Opus permitidos
5. **Límite de tokens** — Máximo 16,000 tokens por respuesta

## 🚀 Despliegue

### Paso 1 — GitHub (el frontend)

1. Sube todo este repositorio a GitHub
2. Ve a Settings → Pages → Source: "Deploy from a branch" → Branch: `main` → Folder: `/web`
3. Tu app estará en: `https://TU-USUARIO.github.io/Panda/`

### Paso 2 — Render.com (el proxy)

1. Ve a [render.com](https://render.com) e inicia sesión con GitHub
2. Clic en "New +" → "Web Service"
3. Conecta tu repositorio `Panda`
4. Render detectará el `render.yaml` automáticamente
5. Configura las variables de entorno secretas:
   - `ANTHROPIC_API_KEY` = tu key de console.anthropic.com
   - `PANDA_SECRET` = una contraseña segura que tú inventes (ej: `P4nd4-2026-Ur0s4r10!`)
6. Deploy

### Paso 3 — Conectar frontend con proxy

1. Copia la URL de tu servicio en Render (ej: `https://panda-proxy-xxxx.onrender.com`)
2. En `web/index.html`, actualiza estas líneas:
   ```javascript
   const PANDA_API_URL = 'https://panda-proxy-xxxx.onrender.com/v1/messages';
   const PANDA_SECRET  = 'P4nd4-2026-Ur0s4r10!';  // el mismo que pusiste en Render
   ```
3. Haz push a GitHub — listo

## 💻 Desarrollo local

```bash
# 1. Instalar dependencias
pip install -r proxy/requirements.txt

# 2. Configurar variables
set ANTHROPIC_API_KEY=sk-ant-tu-key
set PANDA_SECRET=test123

# 3. Arrancar proxy
uvicorn proxy.panda_proxy:app --port 8000

# 4. Abrir web/index.html en Chrome
```

## 💰 Costos estimados

| Modelo | Por búsqueda | 100 búsquedas/mes |
|--------|-------------|-------------------|
| Haiku  | ~$0.02      | ~$2               |
| Sonnet | ~$0.10      | ~$10              |
| Opus   | ~$0.50      | ~$50              |

---
**Powered by Claude AI + web_search · 2026**
