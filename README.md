# Backend Pedidos 360 - Serverless E-Commerce

Un backend de grado de producción para una plataforma de pedidos de comida, construido con una arquitectura Serverless orientada a eventos en AWS. Está enfocado en alta disponibilidad, seguridad centralizada y resiliencia.

## Arquitectura y Tecnologías

El sistema utiliza un enfoque de microservicios distribuidos, eliminando la necesidad de gestionar servidores tradicionales y optimizando los costos mediante `httpApi`.

*   **Infraestructura:** AWS Lambda, API Gateway (HTTP API V2), Serverless Framework.
*   **Lenguaje:** Python 3.13
*   **Base de Datos:** Amazon DynamoDB (Tablas independientes para Pedidos y Catálogo con facturación PAY_PER_REQUEST).
*   **Eventos y Mensajería:** Amazon SNS (Patrón Pub/Sub para desacoplamiento).
*   **Autenticación y Seguridad:** Microsoft Entra ID (Azure AD) con validación nativa JWT en API Gateway.

## Características Principales

*   **Seguridad Zero-Trust en la Frontera:** Control de acceso validado criptográficamente en API Gateway mediante Entra ID. Las peticiones sin token, con token expirado o de otro tenant son rechazadas con un 401 Unauthorized antes de invocar las funciones Lambda.
*   **Máquina de Estados Finita (FSM):** Lógica estricta de transiciones (CREADO -> ACEPTADO -> EN_PREPARACION -> DESPACHADO -> ENTREGADO) para evitar estados inválidos en el ciclo de vida del pedido.
*   **Arquitectura Orientada a Eventos:** Desacoplamiento de dominios. Cuando un pedido cambia a estado ACEPTADO, la función actualizarEstadoPedido emite un evento SNS. La función interna descontarStockEvento lo escucha asíncronamente y actualiza el inventario, eliminando cuellos de botella síncronos.

## Estructura del Proyecto

    ├── src/
    │   ├── pedidos.py      # Microservicio: Gestión de órdenes y FSM
    │   ├── catalogo.py     # Microservicio: Gestión de productos y eventos SNS
    │   └── utils.py        # Utilidades: CORS global y extracción de Claims JWT
    ├── serverless.yml      # Infraestructura como Código (IaC)
    ├── .env.example        # Plantilla de variables de seguridad
    └── README.md

## Instalación y Despliegue Local

### 1. Prerrequisitos
*   Cuenta de AWS configurada (aws configure).
*   Node.js y NPM instalados.
*   Serverless Framework instalado globalmente: npm install -g serverless

### 2. Configuración de Entorno (Entra ID)
Clona el repositorio y configura las variables de Microsoft Entra ID:

    cp .env.example .env

Edita el archivo .env con las credenciales exactas del Tenant y la App de backend:

    ENTRA_TENANT_ID=tu-tenant-id
    ENTRA_CLIENT_ID=tu-client-id

### 3. Despliegue
Despliega toda la infraestructura (Lambdas, DynamoDB, SNS, API Gateway) con:

    serverless deploy

## API Endpoints (Entorno dev)

URL Base: https://3pl5bh2pv0.execute-api.us-east-1.amazonaws.com

Todas las peticiones privadas deben incluir la cabecera: Authorization: Bearer <TOKEN_JWT>

### Catálogo
| Método | Endpoint | Autorización | Función Lambda |
| :--- | :--- | :--- | :--- |
| **GET** | `/api/catalog` | **Pública** | `listarProductos` |
| **POST** | `/api/catalog` | Protegida | `crearProducto` |
| **PATCH** | `/api/catalog/{id}` | Protegida | `actualizarProducto` |
| **PATCH** | `/api/catalog/{id}/stock` | Protegida | `actualizarStockProducto` |
| **DELETE**| `/api/catalog/{id}` | Protegida | `eliminarProducto` |

### Pedidos
| Método | Endpoint | Autorización | Función Lambda |
| :--- | :--- | :--- | :--- |
| **GET** | `/api/orders` | Protegida | `listarPedidos` |
| **POST** | `/api/orders` | Protegida | `crearPedido` |
| **GET** | `/api/orders/{id}` | Protegida | `obtenerPedido` |
| **PATCH** | `/api/orders/{id}/estado` | Protegida | `actualizarEstadoPedido` |

Nota: La función descontarStockEvento no tiene un endpoint HTTP expuesto, es invocada internamente por AWS SNS

## Sistema de Roles y Autorización 

La identidad es gestionada por Microsoft Entra ID (IDaaS), pero el control de acceso estricto se aplica en cada función Lambda analizando el claim `roles` inyectado en el token JWT. 

Para que el backend aplique correctamente las reglas de negocio, el administrador del Tenant en Azure debe crear y asignar los siguientes App Roles exactos:

*   **Cliente**: Dueño de su información. Puede crear pedidos y consultar exclusivamente su propio historial.
*   **Operador**: Encargado de logística y atención. Puede listar la cola global de pedidos, crear nuevos pedidos (simulando atención en caja) y avanzar la máquina de estados de los pedidos en curso. No tiene permisos de escritura sobre el catálogo.
*   **Administrador**:Tiene control exclusivo y total sobre el CRUD del catálogo (crear, editar, eliminar productos y realizar ajustes manuales de stock). De acuerdo con el flujo de negocio, el administrador no crea pedidos operativamente.

**Excepción de Acceso:** 
La ruta `GET /api/catalog` (listar productos) es de acceso público. No requiere token ni rol, permitiendo que cualquier usuario no autenticado pueda visualizar el menú disponible. 
