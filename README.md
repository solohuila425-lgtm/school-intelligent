# ERP Educativo Enterprise

Base ejecutable para un ERP educativo moderno, multi-tenant y preparado para agentes de IA.

Stack:
- Backend: Python 3.12 + FastAPI + SQLAlchemy 2 + PostgreSQL
- Frontend: React + TypeScript + Vite
- Calidad: pytest, Ruff, mypy, Playwright
- Infraestructura: Docker Compose

Principio: ninguna funcionalidad crítica se considera terminada solo porque compila.
Debe pasar validación, pruebas y controles de seguridad.

## Inicio rápido

1. Copia el ejemplo de entorno:
   ```bash
   cp .env.example .env
   ```
2. Ajusta las credenciales reales para tu entorno local o de despliegue.
3. Inicia la infraestructura local:
   ```bash
   docker compose up --build
   ```
4. En otra terminal, levanta el frontend:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

## Variables de entorno clave

El backend exige un contrato explícito para producción:
- `ENVIRONMENT=production` debe ir con PostgreSQL real
- `DATABASE_URL` no puede apuntar a SQLite en producción
- `REDIS_URL` es obligatorio cuando `RATE_LIMIT_ENABLED=true`
- `JWT_SECRET` debe ser secreto real y no un valor de desarrollo
- `CORS_ORIGINS` debe ser una lista restringida, nunca `*`

Ejemplo mínimo válido:
```env
ENVIRONMENT=development
DATABASE_URL=postgresql+psycopg://erp:password@localhost:5432/erp_educativo
REDIS_URL=redis://localhost:6379/0
API_BASE_URL=http://localhost:8000
JWT_SECRET=replace-with-a-long-random-secret
CORS_ORIGINS=http://localhost:5173,https://school-intelligent-jet.vercel.app
RATE_LIMIT_ENABLED=true
```

El ERP educativo está orientado por defecto a Colombia: `DEFAULT_COUNTRY_CODE=CO`
y `DEFAULT_CURRENCY=COP`. La moneda de una factura sigue siendo configurable
por tenant para soportar expansión multinacional. `verifiq-backend/` es un
servicio separado; su configuración peruana no define la región del ERP.

## Plataformas integradas

### Respuestas de agentes en la pizarra

El worker publica `teacher_response_agent` para cada instrucción de un profesor.
Su resultado incluye `message`, `topic` y `session_id` dentro de `agent_results`;
el frontend lo presenta en el chat interno. Requiere un proveedor LLM configurado.
Si el proveedor falla, el resultado queda marcado como error y no se reemplaza por
un texto simulado.

- VerifiQ se mantiene como servicio aislado en `verifiq-backend/`, con KYC/AML,
	firma, pagos y auditoría propios. Su estado de producción está documentado en
	`verifiq-backend/README.md`.
- La Pizarra Inteligente está incorporada como especificación de alta complejidad
	en `01_documentos_maestros/` y `03_prompts_arranque/`; el agente la mantiene
	pendiente hasta que exista el backend fuente correspondiente.
- Las reglas de integración y los gates de ambos productos están en
	`docs/PLATFORM_COMPLEXITY_INTEGRATION.md`.
