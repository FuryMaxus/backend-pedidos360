# Backend Pedidos 360 - Serverless E-Commerce

Un backend de grado de producción para una plataforma de pedidos e e-commerce de comida, construido sobre una arquitectura **100% Serverless y Orientada a Eventos (EDA)** en AWS. Diseñado bajo principios de alta disponibilidad, seguridad **Zero-Trust**, desacoplamiento de servicios y resiliencia ante fallos.

---

##  Arquitectura y Tecnologías

El sistema utiliza un enfoque de microservicios distribuidos sin servidor, eliminando la gestión de infraestructura y optimizando costos mediante facturación por demanda (*Pay-per-request*).

* **Capa Computacional / Serverless:** AWS Lambda, API Gateway (HTTP API v2), Serverless Framework (Infraestructura como Código - IaC).
* **Lenguaje y SDK:** Python 3.13 / AWS SDK (boto3).
* **Base de Datos:** Amazon DynamoDB (Tablas independientes para Pedidos y Catálogo).
* **Eventos y Mensajería (EDA):** 
  * **Amazon SNS (Pub/Sub):** Tópico central para publicación de eventos de dominio.
  * **Amazon SQS (Queues & DLQs):** Colas de procesamiento asíncrono (q-stock, q-kitchen, q-email, q-invoice) y colas de letras muertas (Dead Letter Queues).
* **Autenticación y Seguridad:** Microsoft Entra ID (Azure AD) con validación nativa de JWT en API Gateway (Scopes) y control de acceso basado en roles en Lambda (RBAC).

---

##  Características Principales

### 1. Seguridad Zero-Trust en Dos Capas (Defensa en Profundidad)
* **Capa Perimetral (API Gateway):** Validación criptográfica nativa de los tokens JWT emitidos por Microsoft Entra ID y verificación de **Scopes** (scp). Peticiones sin token, expiradas o sin los ámbitos requeridos son rechazadas con 401 Unauthorized o 403 Forbidden antes de ejecutar código en Lambda.
* **Capa de Aplicación (Lambda Handler):** Inspección de **App Roles** (roles inyectados en el JWT) para aplicar reglas de negocio granulares según el perfil del usuario.

### 2. Arquitectura Orientada a Eventos (Patrón Fan-Out)
Desacoplamiento total entre microservicios. Cuando un pedido cambia a estado ACEPTADO, la función actualizarEstadoPedido emite un único evento al Tópico SNS (PedidosTopic). SNS distribuye en paralelo el mensaje a múltiples colas SQS de consumo:
* **Inventario:** q-stock -> Invocación asíncrona de descontarStockEvento.
* **Cocina:** q-kitchen -> Invocación asíncrona de ticket-cocina.
* **Notificaciones:** q-email -> Invocación asíncrona de notificar-email.
* **Facturación:** q-invoice -> Invocación asíncrona de generar-boleta.

### 3. Tolerancia a Fallos y Manejo de Errores con Dead Letter Queues (DLQ)
Procesamiento seguro de mensajes asíncronos mediante detección de Poison Pills (datos corruptos o incompletos):
* **Errores Recuperables:** Reintentos automáticos manejados por SQS mediante batchItemFailures.
* **Errores No Recuperables:** Captura explícita vía excepciones de negocio (ErrorNoRecuperable), aislando inmediatamente el mensaje fallido en la cola de muertos correspondiente (q-stock-dlq) para auditoría sin bloquear el flujo principal.

### 4. Microservicio Administrador de Infraestructura Dinámica
Endpoint REST interno construido con boto3 para la orquestación y aprovisionamiento bajo demanda de colas SQS (POST /api/queues y DELETE /api/queues), restringido exclusivamente al rol Administrador.

### 5. Máquina de Estados Finita (FSM)
Transición estricta de estados de pedido para evitar inconsistencias en el ciclo de vida:
CREADO -> ACEPTADO -> EN_PREPARACION -> DESPACHADO -> ENTREGADO

---

##  Estructura del Proyecto

    .
    ├── src/
    │   ├── pedidos.py         # Microservicio: Gestión de órdenes, FSM y publicación SNS
    │   ├── catalogo.py        # Microservicio: CRUD de catálogo y consumidor SQS de stock
    │   ├── notificaciones.py  # Microservicio: Consumidor SQS para envío de correos asíncronos
    │   ├── admin_colas.py     # Microservicio: Gestión dinámica de colas SQS (Boto3)
    │   └── utils.py           # Utilidades: Headers CORS global y extracción de Claims JWT
    ├── serverless.yml         # Infraestructura como Código (IaC en AWS)
    ├── .env.example           # Plantilla de variables de entorno y seguridad
    └── README.md              # Documentación del sistema

---

##  Instalación y Despliegue

### 1. Prerrequisitos
* Cuenta de AWS con credenciales configuradas (aws configure).
* Node.js (v18+) y NPM.
* Serverless Framework instalado globalmente: npm install -g serverless

### 2. Configuración de Entorno (Entra ID)
Clona el repositorio y copia la plantilla de variables de entorno:
    cp .env.example .env

Edita el archivo .env con las credenciales de tu Tenant y App de backend en Microsoft Entra ID:
    ENTRA_TENANT_ID=tu-tenant-id-aqui
    ENTRA_CLIENT_ID=tu-client-id-aqui

### 3. Despliegue de Infraestructura
Despliega toda la arquitectura (API Gateway, Lambdas, DynamoDB, SNS, SQS y DLQs) ejecutando:
    serverless deploy

---

##  API Endpoints (Entorno dev)

URL Base: https://<api-id>.execute-api.us-east-1.amazonaws.com  
Cabecera de Autorización: Authorization: Bearer <TOKEN_JWT>

### Catálogo de Productos
| Método | Endpoint | Autorización / Scope | Rol Requerido | Función Lambda |
| :--- | :--- | :--- | :--- | :--- |
| GET | /api/catalog | Pública | Ninguno | listarProductos |
| POST | /api/catalog | Protegida (catalog.write) | Administrador | crearProducto |
| PATCH | /api/catalog/{id} | Protegida (catalog.write) | Administrador | actualizarProducto |
| PATCH | /api/catalog/{id}/stock| Protegida (catalog.write) | Administrador | actualizarStockProducto |
| DELETE| /api/catalog/{id} | Protegida (catalog.write) | Administrador | eliminarProducto |

### Gestión de Pedidos
| Método | Endpoint | Autorización / Scope | Rol Requerido | Función Lambda |
| :--- | :--- | :--- | :--- | :--- |
| GET | /api/orders | Protegida (orders.read) | Cliente / Operador | listarPedidos |
| POST | /api/orders | Protegida (orders.write) | Cliente / Operador | crearPedido |
| GET | /api/orders/{id} | Protegida (orders.read) | Cliente / Operador | obtenerPedido |
| PATCH | /api/orders/{id}/estado| Protegida (orders.write)| Operador | actualizarEstadoPedido |

### Microservicio Administrador (Gestión de Infraestructura SQS)
| Método | Endpoint | Autorización / Scope | Rol Requerido | Función Lambda |
| :--- | :--- | :--- | :--- | :--- |
| POST | /api/queues | Protegida (catalog.write) | Administrador | crearCola |
| DELETE| /api/queues | Protegida (catalog.write) | Administrador | eliminarCola |

Nota sobre Consumidores Asíncronos: Las funciones descontarStockEvento, ticket-cocina, notificar-email y generar-boleta no exponen endpoints HTTP. Son activadas automáticamente por eventos de sus respectivas colas SQS tras el disparo de SNS.

---

##  Sistema de Roles y Autorización (RBAC + Scopes)

La autenticación es delegada a **Microsoft Entra ID (IDaaS)**. El control de acceso se ejecuta analizando las demandas (claims) inyectadas en el JWT:

* **Cliente:** Acceso restringido a sus propios recursos. Puede crear pedidos y consultar únicamente su historial de compras.
* **Operador:** Encargado de la logística operativa. Puede consultar la cola global de pedidos, crear pedidos en caja y avanzar los estados del pedido (ACEPTADO, EN_PREPARACION, etc.). No posee permisos para modificar el catálogo ni la infraestructura.
* **Administrador:** Control total sobre el mantenimiento del catálogo de productos (CRUD) y la administración dinámica de colas SQS.
