import json
import uuid
import os
import boto3
from src.utils import CORS_HEADERS, DecimalEncoder, obtener_identidad

dynamodb = boto3.resource('dynamodb')
sqs_client = boto3.client('sqs')
tabla_catalogo = dynamodb.Table(os.environ.get('TABLA_CATALOGO'))

class ErrorNoRecuperable(Exception):
    pass

def crear_producto(event, context):
    roles, _ = obtener_identidad(event)
    
    if "Administrador" not in roles:
        return {
            "statusCode": 403,
            "body": json.dumps({"error": "Acceso denegado"}),
            "headers": CORS_HEADERS
            }

    body = json.loads(event.get("body", "{}")) if event.get("body") else {}
    
    if not body.get("nombre") or not body.get("precio"):
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Faltan datos requeridos (nombre, precio)"}),
            "headers": CORS_HEADERS
            }
        
    producto = {
        "id": str(uuid.uuid4()),
        "nombre": body.get("nombre"),
        "precio": body.get("precio"),
        "stock": body.get("stock", 0) 
    }
    
    tabla_catalogo.put_item(Item=producto)
    return {
        "statusCode": 201,
        "body": json.dumps(producto,cls=DecimalEncoder),
        "headers": CORS_HEADERS
    }

def listar_productos(event, context):
    respuesta = tabla_catalogo.scan()
    productos = respuesta.get("Items", [])
    
    return {
        "statusCode": 200,
        "body": json.dumps(productos, cls=DecimalEncoder),
        "headers": CORS_HEADERS
        }

def actualizar_stock(event, context):
    roles, _ = obtener_identidad(event)
    if "Administrador" not in roles:
        return {
            "statusCode": 403,
            "body": json.dumps({"error": "Acceso denegado"}),
            "headers": CORS_HEADERS
            }

    path_params = event.get("pathParameters", {}) or {}
    producto_id = path_params.get("id")
    body = json.loads(event.get("body", "{}")) if event.get("body") else {}
    
    variacion_stock = body.get("cantidad") 
    
    if not variacion_stock or not isinstance(variacion_stock, int):
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Debe enviar una 'cantidad' entera."}),
            "headers": CORS_HEADERS
            }

    try:
        respuesta = tabla_catalogo.update_item(
            Key={"id": producto_id},
            UpdateExpression="ADD stock :val",
            ExpressionAttributeValues={":val": variacion_stock},
            ReturnValues="UPDATED_NEW"
        )
        nuevo_stock = int(respuesta["Attributes"]["stock"])
        
        if nuevo_stock < 0:
            tabla_catalogo.update_item(
                Key={"id": producto_id},
                UpdateExpression="ADD stock :val",
                ExpressionAttributeValues={":val": abs(variacion_stock)}
            )
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Stock insuficiente"}),
                "headers": CORS_HEADERS
                }

        return {
            "statusCode": 200,
            "body": json.dumps({"id": producto_id, "nuevo_stock": nuevo_stock}),
            "headers": CORS_HEADERS
            }
        
    except Exception as e:
         return {
            "statusCode": 500,
            "body": json.dumps({"error": "Error al actualizar stock"}),
            "headers": CORS_HEADERS
            }

def actualizar_producto(event, context):
    roles, _ = obtener_identidad(event)
    
    if "Administrador" not in roles:
        return {
            "statusCode": 403,
            "body": json.dumps({"error": "Acceso denegado"}),
            "headers": CORS_HEADERS
        }

    producto_id = event.get("pathParameters", {}).get("id")
    body = json.loads(event.get("body", "{}")) if event.get("body") else {}
    
    expresion_update = []
    valores = {}
    
    if "nombre" in body:
        expresion_update.append("nombre = :nombre")
        valores[":nombre"] = body["nombre"]
        
    if "precio" in body:
        expresion_update.append("precio = :precio")
        valores[":precio"] = body["precio"]
        
    if not expresion_update:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "No se enviaron valores para actualizar"}),
            "headers": CORS_HEADERS
        }

    try:
        respuesta = tabla_catalogo.update_item(
            Key={"id": producto_id},
            UpdateExpression="SET " + ", ".join(expresion_update),
            ExpressionAttributeValues=valores,
            ReturnValues="ALL_NEW" 
        )
        
        producto_actualizado = respuesta.get("Attributes", {})
        
        return {
            "statusCode": 200,
            "body": json.dumps(producto_actualizado, cls=DecimalEncoder), 
            "headers": CORS_HEADERS
        }
    except Exception as e:
        print(f"Error al actualizar: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Error interno del servidor"}),
            "headers": CORS_HEADERS
        }

def eliminar_producto(event, context):
    roles, _ = obtener_identidad(event)
    
    if "Administrador" not in roles:
        return {
            "statusCode": 403,
            "body": json.dumps({"error": "Acceso denegado"}),
            "headers": CORS_HEADERS
        }

    producto_id = event.get("pathParameters", {}).get("id")

    try:
        tabla_catalogo.delete_item(
            Key={"id": producto_id}
        )
        return {
            "statusCode": 200,
            "body": json.dumps({"mensaje": f"Producto {producto_id} eliminado exitosamente"}),
            "headers": CORS_HEADERS
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Error interno"}),
            "headers": CORS_HEADERS
        }

def descontar_stock_evento(event, context):
    """
    Consumidor asíncrono para SQS.
    Maneja confirmación de mensajes y envío a DLQ para errores no recuperables.
    """
    batch_item_failures = []
    dlq_url = os.environ.get('DLQ_STOCK_URL')
    
    for record in event.get('Records', []):
        message_id = record['messageId']
        intentos = record.get('attributes', {}).get('ApproximateReceiveCount', 1)
        
        try:
            msg = json.loads(record['body'])
            print(f"Procesando evento de stock. Intento n° {intentos}: {msg}")
            
            items_vendidos = msg.get("items_vendidos")
            pedido_id = msg.get("pedidoId")
            
            if not items_vendidos or not pedido_id:
                raise ErrorNoRecuperable("Mensaje inválido: Falta 'pedidoId' o 'items_vendidos'.")
            
            for item in items_vendidos:
                producto_id = item.get("producto_id")
                cantidad = item.get("cantidad")
                
                if not producto_id or not cantidad:
                    raise ErrorNoRecuperable(f"El item no tiene producto_id o cantidad válida: {item}")
                
                tabla_catalogo.update_item(
                    Key={"id": producto_id},
                    UpdateExpression="ADD stock :val",
                    ExpressionAttributeValues={":val": -int(cantidad)}
                )
                print(f"Stock descontado: -{cantidad} para el producto {producto_id} del pedido {pedido_id}")
            
            
        except ErrorNoRecuperable as e:
            print(f"Error NO recuperable. Enviando mensaje {message_id} a DLQ: {str(e)}")
            if dlq_url:
                sqs_client.send_message(
                    QueueUrl=dlq_url,
                    MessageBody=record['body']
                )
            
        except Exception as e:
            print(f"Error recuperable (ej. DynamoDB bloqueado). Reintentando mensaje {message_id}: {str(e)}")
            batch_item_failures.append({"itemIdentifier": message_id})
            
    return {"batchItemFailures": batch_item_failures}