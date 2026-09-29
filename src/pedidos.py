import json
import uuid
import os
import boto3
from datetime import datetime
from src.utils import CORS_HEADERS, DecimalEncoder, obtener_identidad

dynamodb = boto3.resource('dynamodb')
tabla_pedidos = dynamodb.Table(os.environ.get('TABLA_PEDIDOS'))
tabla_catalogo = dynamodb.Table(os.environ.get('TABLA_CATALOGO'))
sns = boto3.client('sns')

ESTADOS_VALIDOS = os.environ.get('ESTADOS_PERMITIDOS', '').split(',')
TRANSICIONES_PERMITIDAS = {
    "CREADO": ["ACEPTADO", "CANCELADO"],
    "ACEPTADO": ["EN_PREPARACION", "CANCELADO"],
    "EN_PREPARACION": ["DESPACHADO", "CANCELADO"],
    "DESPACHADO": ["ENTREGADO"],
    "ENTREGADO": [], 
    "CANCELADO": []  
}

def crear_pedido(event, context):
    roles, user_id = obtener_identidad(event)
    
    if "Cliente" not in roles and "Operador" not in roles:
        return {
            "statusCode": 403,
            "body": json.dumps({"error": "Acceso denegado"}),
            "headers": CORS_HEADERS
            }

    body = json.loads(event.get("body", "{}")) if event.get("body") else {}
    
    if not body.get("items"):
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Faltan los items del pedido"}),
            "headers": CORS_HEADERS
            }
    
    cliente_id = user_id if "Cliente" in roles else body.get("cliente_id", user_id)
    
    nuevo_pedido = {
        "id": str(uuid.uuid4()),
        "cliente_id": cliente_id,
        "items": body.get("items"),
        "estado": "CREADO",
        "fecha_creacion": datetime.now().isoformat()
    }
    
    tabla_pedidos.put_item(Item=nuevo_pedido)
    return {
        "statusCode": 201,
        "body": json.dumps(nuevo_pedido, cls=DecimalEncoder),
        "headers": CORS_HEADERS
        }

def listar_pedidos(event, context):
    roles, user_id = obtener_identidad(event)
    
    if not roles or ("Cliente" not in roles and "Operador" not in roles and "Administradoristrador" not in roles):
        return {
            "statusCode": 403,
            "body": json.dumps({"error": "Acceso denegado"}),
            "headers": CORS_HEADERS
        }

    query_params = event.get("queryStringParameters") or {}
    filtro_cliente = query_params.get("cliente_id")

    if "Cliente" in roles and "Operador" not in roles and "Administradoristrador" not in roles:
        filtro_cliente = user_id

    try:
        if filtro_cliente:
            respuesta = tabla_pedidos.scan(
                FilterExpression="cliente_id = :cliente_id",
                ExpressionAttributeValues={":cliente_id": filtro_cliente}
            )
        else:
            respuesta = tabla_pedidos.scan()
            
        pedidos = respuesta.get("Items", [])
        
        return {
            "statusCode": 200,
            "body": json.dumps(pedidos, cls=DecimalEncoder),
            "headers": CORS_HEADERS
        }
        
    except Exception as e:
        print(f"Error al listar pedidos: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Error interno al obtener los pedidos"}),
            "headers": CORS_HEADERS
        }

def obtener_pedido(event, context):
    roles, user_id = obtener_identidad(event)
    path_params = event.get("pathParameters", {}) or {}
    pedido_id = path_params.get("id")
    
    respuesta = tabla_pedidos.get_item(Key={"id": pedido_id})
    pedido = respuesta.get("Item")
    
    if not pedido:
        return {
            "statusCode": 404,
            "body": json.dumps({"error": "Pedido no encontrado"}),
            "headers": CORS_HEADERS
            }
        
    if "Cliente" in roles and "Administradoristrador" not in roles and "Operador" not in roles:
        if pedido.get("cliente_id") != user_id:
            return {
                "statusCode": 403,
                "body": json.dumps({"error": "Acceso denegado"}),
                "headers": CORS_HEADERS
                }
            
    return {
        "statusCode": 200,
        "body": json.dumps(pedido,cls=DecimalEncoder),
        "headers": CORS_HEADERS
        }


def actualizar_estado(event, context):
    roles, _ = obtener_identidad(event)
    
    if "Operador" not in roles and "Administradoristrador" not in roles:
        return {
            "statusCode": 403,
            "body": json.dumps({"error": "Acceso denegado"}),
            "headers": CORS_HEADERS
            }
        
    path_params = event.get("pathParameters", {}) or {}
    pedido_id = path_params.get("id")
    body = json.loads(event.get("body", "{}")) if event.get("body") else {}
    nuevo_estado = body.get("estado")

    respuesta = tabla_pedidos.get_item(Key={"id": pedido_id})
    pedido = respuesta.get("Item")

    if not pedido:
        return {
            "statusCode": 404,
            "body": json.dumps({"error": "Pedido no encontrado"}),
            "headers": CORS_HEADERS
            }

    estado_actual = pedido.get("estado")
    
    if nuevo_estado not in ESTADOS_VALIDOS:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Estado inválido"}),
            "headers": CORS_HEADERS
            }
        
    if nuevo_estado not in TRANSICIONES_PERMITIDAS.get(estado_actual, []):
        return {
            "statusCode": 400,
            "body": json.dumps({
                "error": f"Transición no permitida. No se puede pasar de '{estado_actual}' a '{nuevo_estado}'."
            }),
            "headers": CORS_HEADERS
        }

    if nuevo_estado == "ACEPTADO":
        try:
            for item in pedido.get("items", []):
                prod_id = item.get("producto_id")
                cantidad_requerida = item.get("cantidad")
                resp_cat = tabla_catalogo.get_item(Key={"id": prod_id})
                producto = resp_cat.get("Item")
                
                if not producto:
                    return {
                        "statusCode": 400,
                        "body": json.dumps({"error": f"El producto {prod_id} no existe en el catálogo."}),
                        "headers": CORS_HEADERS
                    }
                    
                if int(producto.get("stock", 0)) < cantidad_requerida:
                    return {
                        "statusCode": 400,
                        "body": json.dumps({"error": f"Stock insuficiente para la ID {prod_id}. Disponible: {producto.get('stock')}"}),
                        "headers": CORS_HEADERS
                    }
        except Exception as e:
            print(f"Error al verificar stock: {str(e)}")
            return {
                "statusCode": 500,
                "body": json.dumps({"error": "Error interno verificando el inventario."}),
                "headers": CORS_HEADERS
            }
    
    tabla_pedidos.update_item(
        Key={"id": pedido_id},
        UpdateExpression="SET estado = :nuevo_estado",
        ExpressionAttributeValues={":nuevo_estado": nuevo_estado}
    )

    pedido["estado"] = nuevo_estado    

    if nuevo_estado == "ACEPTADO":
        try:
            sns.publish(
                TopicArn=os.environ['TOPIC_ARN_SNS'],
                Message=json.dumps({
                    "items_vendidos": pedido["items"] 
                }, cls=DecimalEncoder)
            )
            print("Evento publicado en SNS exitosamente")
            
        except Exception as e:
            print(f"Error crítico en SNS. Iniciando Rollback: {str(e)}")
            
            tabla_pedidos.update_item(
                Key={"id": pedido_id},
                UpdateExpression="SET estado = :estado",
                ExpressionAttributeValues={":estado": "CANCELADO"}
            )
            
            return {
                "statusCode": 500,
                "body": json.dumps({
                    "error": "Error interno. El pedido fue Cancelado automáticamente porque no se pudo verificar el inventario."
                }),
                "headers": CORS_HEADERS
            }

    return {
        "statusCode": 200,
        "body": json.dumps(pedido,cls=DecimalEncoder),
        "headers": CORS_HEADERS
        }