import json
import os
import boto3

sqs_client = boto3.client('sqs')

class ErrorNoRecuperable(Exception):
    """Excepción para errores de negocio o datos inválidos que no deben reintentarse."""
    pass


def enviar_email(event, context):
    return procesar_mensajes_sqs(event, os.environ['DLQ_EMAIL_URL'], "Email enviado")

def imprimir_ticket(event, context):
    return procesar_mensajes_sqs(event, os.environ['DLQ_KITCHEN_URL'], "Ticket de cocina impreso")

def generar_boleta(event, context):
    return procesar_mensajes_sqs(event, os.environ['DLQ_INVOICE_URL'], "Boleta generada")


def procesar_mensajes_sqs(event, dlq_url, accion_log):
    batch_item_failures = []
    
    for record in event.get('Records', []):
        message_id = record['messageId']
        intentos = record['attributes'].get('ApproximateReceiveCount', 1)
        
        try:
            msg = json.loads(record['body'])
            print(f"Mensaje recibido. Intento n° {intentos}: {msg}")
            
            if not msg.get('pedidoId'):
                raise ErrorNoRecuperable("Mensaje inválido: Falta atributo 'pedidoId'")
                
            if msg.get('simularError'):
                raise Exception("Error simulado: Falla temporal de conexión")
                
            print(f"{accion_log} con éxito para el pedido {msg['pedidoId']}")
            
        except ErrorNoRecuperable as e:
            print(f"Error NO recuperable. Enviando a DLQ: {message_id} - {str(e)}")
            sqs_client.send_message(
                QueueUrl=dlq_url,
                MessageBody=record['body']
            )
            
        except Exception as e:
            print(f"Error recuperable. Reintentando mensaje: {message_id} - {str(e)}")
            batch_item_failures.append({"itemIdentifier": message_id})
            
    return {"batchItemFailures": batch_item_failures}