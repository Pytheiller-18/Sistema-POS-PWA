# SISTEMA POS PWA

> **Sistema de Punto de Venta (POS) Ligero, Multi-Tenant y Offline-First con Arquitectura PWA y Sincronización en la Nube.**

[![Python](https://img.shields.io/badge/Python-3.13+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.1.3-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![MySQL](https://img.shields.io/badge/MySQL-8.0+-4479A1?style=for-the-badge&logo=mysql&logoColor=white)](https://www.mysql.com/)
[![PWA](https://img.shields.io/badge/PWA-Offline--First-5A0FC8?style=for-the-badge&logo=pwa&logoColor=white)](https://web.dev/progressive-web-apps/)
[![IndexedDB](https://img.shields.io/badge/IndexedDB-Local--First-F7DF1E?style=for-the-badge&logo=javascript&logoColor=black)](https://developer.mozilla.org/es/docs/Web/API/IndexedDB_API)

---

## 📌 Descripción del Proyecto

**SISTEMA POS PWA** es una solución integral de Punto de Venta diseñada bajo el paradigma **Local-First / Offline-First**, garantizando que una tienda o comercio minorista pueda continuar operando y facturando ventas aún cuando la conexión a internet sea inestable o inexistente. Al restablecerse la red, las transacciones se sincronizan de manera transparente e idempotente con el servidor central.

### 🌟 Pilares y Capacidades Clave

1. **Arquitectura Offline-First (PWA):**
   - El catálogo de productos y las ventas se gestionan localmente en el navegador mediante **IndexedDB** y **Service Workers**.
   - Funcionamiento continuo sin depender de la nube.
   - Idempotencia garantizada por `client_sync_id` único para evitar cobros o deducciones de inventario duplicadas en reintentos.

2. **Aislamiento Multi-Tenant (SaaS):**
   - Múltiples tiendas operan sobre la misma infraestructura con estricta separación de datos mediante `tenant_id` obligatorio a nivel de modelos, middleware y consultas relacionales.
   - Prevención exhaustiva de vulnerabilidades IDOR (*Insecure Direct Object References*).

3. **Adaptabilidad Total (Móvil & Escritorio):**
   - **Vista Celular:** Diseño táctil ultra-rápido, chips de categoría deslizables, escáner simulado y carrito flotante tipo cajón inferior.
   - **Vista Computador (Escritorio):** Pantalla partida clásica de caja (*Dual-Pane*), catálogo a la izquierda y panel de orden/cobro permanente a la derecha con atajos rápidos de efectivo.

4. **Analíticas y Reportes de Ganancias:**
   - Métricas en tiempo real: Ventas del día, ticket promedio, ventas acumuladas del mes (comparativa con mes previo), desglose anual de 12 meses, top 5 productos de mayor rotación y cálculo de utilidad neta (`Ingresos - Costos Históricos`).

---

## 📑 Estructura de Directorios

El proyecto se encuentra desacoplado en dos módulos principales:

```text
SISTEMA-POS-PWA/
├── backend/                                   # Capa de API RESTful, Lógica de Negocio y Persistencia
│   ├── app/
│   │   ├── __init__.py                        # Fábrica de aplicaciones Flask y registro de rutas
│   │   ├── config.py                          # Configuración MySQL / SQLite fallback y JWT
│   │   ├── extensions.py                      # Instancias de SQLAlchemy y Flask-CORS
│   │   ├── middlewares/
│   │   │   └── auth.py                        # Decorador @tenant_required y validación JWT
│   │   ├── models/                            # Entidades relacionales del sistema
│   │   │   ├── tenant.py                      # Tiendas / Empresas aisladas
│   │   │   ├── user.py                        # Usuarios (Admin, Cajero, Manager)
│   │   │   ├── product.py                     # Categorías y Productos con stock
│   │   │   ├── sale.py                        # Ventas (Sales) e ítems con costo histórico
│   │   │   └── sync_log.py                    # Auditoría de sincronización offline
│   │   ├── routes/                            # Endpoints modulares (Blueprints)
│   │   │   ├── auth.py                        # Login, registro de tenant y usuarios
│   │   │   ├── products.py                    # CRUD de catálogo y consulta delta ?since=...
│   │   │   ├── sales.py                       # Registro de ventas y detalle para ticket
│   │   │   ├── sync.py                        # Sincronización de lotes offline (/sales-batch)
│   │   │   └── reports.py                     # Reportes (hoy, mensual, anual, utilidades)
│   │   └── services/
│   │       ├── sale_service.py                # Transacciones ACID, stock e idempotencia
│   │       └── report_service.py              # Agregaciones financieras y márgenes
│   ├── tests/
│   │   └── test_backend.py                    # Suite de 6 pruebas de aislamiento y seguridad
│   ├── requirements.txt                       # Dependencias de Python
│   ├── run.py                                 # Servidor con auto-siembra de datos demo
│   └── schema.sql                             # DDL completo para MySQL 8.0+
│
├── frontend/                                  # Aplicación Cliente PWA (Offline-First)
│   ├── index.html                             # Terminal de Punto de Venta responsiva
│   ├── manifest.json                          # Web App Manifest instalable en Android, iOS, PC
│   ├── sw.js                                  # Service Worker (Cache App Shell & Fetch fallback)
│   ├── assets/
│   │   └── icon.svg                           # Icono vectorial escalable de la PWA
│   ├── css/
│   │   ├── variables.css                      # Design Tokens y tema oscuro de alto contraste
│   │   ├── layout.css                         # Grids responsivos (Mobile & Desktop Dual-Pane)
│   │   └── components.css                     # Tarjetas, teclado de cobro, modales y ticket impreso
│   └── js/
│       ├── db.js                              # Envoltorio IndexedDB (almacén local del catálogo y cola)
│       ├── api.js                             # Cliente HTTP con JWT y detección de fallos
│       ├── sync.js                            # Gestor de sincronización offline y deltas
│       └── app.js                             # Coordinador de vistas, carrito y cobro
│
├── index.html                                 # Portal de documentación y ficha técnica de investigación
├── .gitignore                                 # Reglas de exclusión de Git
└── README.md                                  # Documentación técnica del proyecto
```

---

## 🚀 Puesta en Marcha Rápida (Local)

### 1. Iniciar el Backend (Python / Flask)

El backend cuenta con detección automática: si no hay un servidor MySQL configurado localmente, utiliza SQLite como motor de desarrollo sin necesidad de configuración adicional.

1. Abre una terminal e ingresa a la carpeta `backend`:
   ```powershell
   cd backend
   ```
2. Instala las dependencias:
   ```powershell
   python -m pip install -r requirements.txt
   ```
3. Inicia el servidor API:
   ```powershell
   python run.py
   ```
   *El servidor inicializará las tablas y cargará datos de demostración si es la primera ejecución.*
   *La API estará escuchando en `http://localhost:5000`.*

#### 🔑 Credenciales Demo Iniciales:
- **Administrador:** `admin@pos.com` | Contraseña: `admin123`
- **Cajero:** `cajero@pos.com` | Contraseña: `cajero123`

---

### 2. Iniciar el Frontend (PWA)

1. Abre el archivo `frontend/index.html` en tu navegador preferido (Chrome, Edge, Firefox, Safari) o utiliza un servidor estático local:
   ```powershell
   # Opción directa en Windows:
   Start-Process frontend/index.html
   ```
2. Puedes instalar la aplicación como una PWA nativa haciendo clic en el icono de instalación de la barra de direcciones del navegador.

---

## 🧪 Verificación y Pruebas del Backend

Para validar la seguridad multi-tenant, la deducción de inventario, la idempotencia contra ventas duplicadas y los cálculos financieros:

```powershell
python backend/tests/test_backend.py
```

---

## 📡 Referencia de la API RESTful

| Método | Endpoint | Descripción | Roles |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/login` | Autenticación y entrega de token JWT | Público |
| `POST` | `/api/v1/auth/register-tenant` | Registro de nueva tienda y administrador | Público |
| `GET` | `/api/v1/auth/me` | Información del usuario y tienda activa | Todos |
| `GET` | `/api/v1/products` | Catálogo de productos (con soporte `?since=...`) | Todos |
| `POST` | `/api/v1/products` | Creación de nuevo producto | Admin/Manager |
| `PUT` | `/api/v1/products/<id>` | Actualización de producto | Admin/Manager |
| `POST` | `/api/v1/sales` | Registro directo de venta | Todos |
| `POST` | `/api/v1/sync/sales-batch` | Sincronización de lote de ventas offline | Todos |
| `GET` | `/api/v1/reports/today` | Ventas y tickets del día | Admin/Manager |
| `GET` | `/api/v1/reports/monthly` | Resumen mensual y comparativa | Admin/Manager |
| `GET` | `/api/v1/reports/profit` | Utilidad neta y margen | Admin |

---

## 📄 Licencia y Autores

Proyecto desarrollado como parte de la propuesta de investigación aplicada y sistematización de microempresas locales con arquitectura **Progressive Web App (PWA)**.
