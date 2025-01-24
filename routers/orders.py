from fastapi import FastAPI, HTTPException, Query, APIRouter
from pydantic import BaseModel
from datetime import datetime, timedelta
import logging
import httpx
import asyncio
from aiohttp import ClientSession
import json
import database

router = APIRouter()

class OrderStatusUpdate(BaseModel):
    orderStatus: str

class OrderUpdate(BaseModel):
    orderID: int
    orderStatus: str

# helper function to send order to ims
async def send_to_ims_api(ims_api_url: str, payload: dict):
    try:
        logging.info(f'Sending data to IMS API: {ims_api_url}')
        logging.debug(f'Payload: {payload}')
        
        async with httpx.AsyncClient() as client:
            response = await client.post(ims_api_url, json=payload)
            response.raise_for_status()
            logging.info(f'Response received from IMS API: {response.json()}')
            return response.json()
    
    except httpx.HTTPStatusError as http_err:
        logging.error(f"HTTP error occured: {http_err.response.status_code} - {http_err.response.text}")
        raise HTTPException(status_code=500, detail=f"IMS API error:{http_err.response.text}")
    except Exception as e:
        logging.error(f"Error sending data to IMS API: {e}")
        raise HTTPException(status_code=500, detail=f'Error sending data to IMS API:{e}')

def parse_datetime(date_str):
    """Convert string timestamp to datetime format for SQL Server."""
    if isinstance(date_str, str):
        try:
            return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')  # Standard format
        except ValueError:
            try:
                return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S.%f')  # Handles milliseconds
            except ValueError:
                return datetime.strptime(date_str, '%Y-%m-%d')  # Handles date only
    return date_str  # If already datetime, return as-is


# receive order from ims
@router.post('/vms/orders')
async def receive_order(order: dict):
    conn = None
    try:
        # extract order details
        customer_id = order.get('customerID')
        order_date = parse_datetime(order.get('orderDate', datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')))
        order_status = 'Pending'
        products = order.get('products', [])

        # validate the incoming data
        if not customer_id or not products:
            raise HTTPException(status_code=400, detail="Invalid order data.")

        conn = await database.get_db_connection()
        cursor = await conn.cursor()

        # save order in VMS
        await cursor.execute('''insert into purchaseOrders (orderDate, orderStatus,
                             statusDate, customerID)
                             output inserted.orderID
                             values (?,?,?,?)''',
                             (order_date, order_status, datetime.utcnow(), customer_id))
        
        order_id = await cursor.fetchone()
        if not order_id:
            raise HTTPException(status_code=500, detail='Failed to create purchase order.')

        # insert purchase order details
        for product in products:
            product_id = product.get('productID')
            quantity = product.get('quantity')
            expected_date = parse_datetime(product.get('expectedDate', (datetime.utcnow() + timedelta(days=7))))

            if not product_id or not quantity:
                raise HTTPException(status_code=400, detail="invalid product details")
            
            await cursor.execute(
                ''' insert into purchaseOrderDetails 
                (orderQuantity, expectedDate, productID, orderID)
                values (?, ?, ?, ?)''',
                (quantity, expected_date, product_id, order_id[0])
            )
        await conn.commit()
        return {"message": "Order received successfully.", "orderID": order_id[0]}
    except Exception as e:
        logging.error(f"Error receiving order: {e}")
        raise HTTPException(status_code=500, detail=f"Error receiving order: {e}")
    finally:
        if conn:
            await conn.close()


# confirm or reject order
@router.put('/vms/orders/{orderID}/confirm')
async def confirm_order(orderID: int, order_status_update: OrderStatusUpdate):
    conn = None
    try:
        conn = await database.get_db_connection()
        cursor = await conn.cursor()

        # validate order and its current status
        await cursor.execute(
            '''select orderStatus 
            from purchaseOrders 
            where orderID =?''',
            (orderID,)
        )
        order = await cursor.fetchone()
        if not order:
            raise HTTPException(status_code=404, detail="order not found.")
        # only allow "Pending" orders to be confirmed or rejected
        if order[0] != 'Pending':
            raise HTTPException(status_code=400, detail="Order is not in 'Pending' status")
        
        # validate the status provided
        status = order_status_update.orderStatus
        if status not in ["Confirmed", "Rejected"]:
            raise HTTPException(status_code=400, detail="Invalid order status. Must be 'Confirmed' or 'Rejected' only.")
        
        # fetch order details for the products
        await cursor.execute(
            '''select productID, orderQuantity
            from purchaseOrderDetails 
            where orderID = ?''',
            (orderID,)
        )
        products = await cursor.fetchall()

        # check the availability of product variants
        for product in products: 
            product_id = product[0]
            order_quantity = product[1]

            # fetch available variant for the product
            variant_query = f'''select top ({order_quantity}) pv.barcode, pv.productCode, p.productName, 
                                       p.category, p.size
                                       from productVariants pv
                                       join Products p 
                                       on pv.productID = p.productID
                                       where pv.productID = ? AND pv.isAvailable = 1
                                       order by pv.variantID asc'''
            await cursor.execute(variant_query, (product_id,))
            variants = await cursor.fetchall()

            # check if there are enough available variants
            if len(variants) < order_quantity:
                raise HTTPException(status_code=400, detail=f"not enough available variants for productID {product_id}. Required: {order_quantity}, Available: {len(variants)}")
        
        # prepare the payload for IMS if the status is "Confirmed"
        ims_api_url = "http://127.0.0.1:8000/receive-orders/ims/orders/confirm"
        ims_payload = {"orderID": orderID, "orderStatus": status}

        # send the confirmation or rejection to IMS and wait for a response
        ims_response = await send_to_ims_api(ims_api_url, ims_payload)

        # update the status in VMS immediately after receiving the response from IMS
        await cursor.execute(
            '''update purchaseOrders 
            set orderStatus = ?, statusDate = ?
            where orderID = ? ''',
            (status, datetime.utcnow(), orderID)
        )
        await conn.commit()

        return {'message': f"order {orderID} has been {status} in VMS", 'imsResponse': ims_response}
    
    except Exception as e:
        logging.error(f"error confirming order: {e}")
        raise HTTPException(status_code=500, detail=f"error processing order: {e}")
    finally:
        if conn:
            await conn.close()

@router.put('/vms/orders/{orderID}/toship')
async def mark_to_ship(orderID: int):
    conn = None
    try:
        conn = await database.get_db_connection()
        cursor = await conn.cursor()

        # validate order sttaus in VMS
        await cursor.execute(
            '''select orderStatus
            from purchaseOrders
            where orderID = ?''',
            (orderID,)
        )
        order = await cursor.fetchone()
        if not order or order[0] != 'Confirmed':
            raise HTTPException(status_code=400, detail="order is not in 'Confirmed' status")
        
        # update to "To Ship" in VMS
        await cursor.execute(
            '''update purchaseOrders
            set orderStatus = 'To Ship', 
            statusDate = ?
            where orderID = ?''',
            (datetime.utcnow(), orderID)
        )
        await conn.commit()

        # after updatimg VMS, also update IMS with the 'To Ship' status
        ims_url = 'http://127.0.0.1:8000/receive-orders/ims/orders/ToShip'  

        ims_payload = {
            "orderID": orderID,
            "orderStatus": "To Ship"
        }

        # make the API call to IMS to update the order status
        async with httpx.AsyncClient() as client:
            ims_response = await client.post(ims_url, json = ims_payload)
            ims_response.raise_for_status()
        
        # log the ims response for debuggin
        logging.info(f"IMS response: {ims_response.status_code} - {ims_response.text}")

        return {'message': f"order {orderID} marked as 'To Ship' in VMS and updated in IMS."}
    
    except httpx.HTTPStatusError as http_err:
        logging.error(f"HTTP Error while communication with IMS: {http_err}")
        raise HTTPException(status_code=500, detail=f'Error processing the update: {http_err.response.status_code} - {http_err.response.text}')
    except Exception as e: 
        logging.error(f"UNexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing the update: {e}")
    finally:
        if conn:
            await conn.close()

# Define the send_to_ims_api_with_retries function
async def send_to_ims_api_with_retries(url, payload, retries=3, delay=2):
    for attempt in range(retries):
        try:
            async with ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        return await response.json()
        except Exception as e:
            logging.error(f"Attempt {attempt + 1} failed: {e}")
        await asyncio.sleep(delay)
    raise HTTPException(status_code=500, detail="Failed to send data to IMS after multiple attempts.")

@router.put('/vms/orders/{orderID}/ship')
async def ship_order(orderID: int):
    conn = None
    try:
        conn = await database.get_db_connection()
        cursor = await conn.cursor()

        # Validate order status
        await cursor.execute(
            '''SELECT orderStatus
               FROM purchaseOrders
               WHERE orderID = ?''',
            (orderID,)
        )
        order = await cursor.fetchone()
        if not order or order[0] != 'To Ship':
            raise HTTPException(status_code=400, detail="Order is not in 'To Ship' status.")

        # Fetch products and order quantities
        await cursor.execute(
            '''SELECT pod.productID, pod.orderQuantity
               FROM purchaseOrderDetails pod
               WHERE pod.orderID = ?''',
            (orderID,)
        )
        products = await cursor.fetchall()
        if not products:
            raise HTTPException(status_code=404, detail="No products found for this order.")

        # Prepare the list of product variants to send to IMS
        variant_data = []
        for product in products:
            product_id, order_quantity = product

            order_quantity = int(order_quantity)

            # Fetch only the required number of product variants (orderQuantity)
            await cursor.execute(
                '''SELECT TOP (?) pv.barcode, pv.productCode, p.productName, p.category, p.size
                   FROM productVariants pv
                   JOIN products p ON pv.productID = p.productID
                   WHERE pv.productID = ? AND pv.isAvailable = 1
                   ORDER BY pv.variantID ASC''',  
                (order_quantity, product_id)
            )
            variants = await cursor.fetchall()
            logging.info(f"Available variants for productID {product_id}: {len(variants)}")
            
            if len(variants) < order_quantity:
                raise HTTPException(
                    status_code=400,
                    detail=f"Not enough available variants for productID {product_id}. "
                           f"Required: {order_quantity}, Available: {len(variants)}"
                )

            # Add the fetched variants to the variant_data list
            variant_data.extend([{
                "barcode": v[0],
                "productCode": v[1],
                "productName": v[2],
                "category": v[3],
                "size": v[4]
            } for v in variants[:order_quantity]])  
            
        # Send the prepared variants to IMS
        ims_api_url = 'http://127.0.0.1:8000/receive-orders/ims/variants/receive'
        payload = {
            'orderID': orderID,
            'orderStatus': 'Shipped',  
            'variants': variant_data
        }
        logging.info(f"Sending payload to IMS: {payload}")
        ims_response = await send_to_ims_api_with_retries(ims_api_url, payload)

        if ims_response.get('status') != 'success':
            raise HTTPException(status_code=500, detail="Failed to send order data to IMS.")

        # Update order status to 'Shipped'
        await cursor.execute(
            '''UPDATE purchaseOrders
               SET orderStatus = 'Shipped', statusDate = ?
               WHERE orderID = ?''',
            (datetime.utcnow(), orderID)
        )

        # Mark selected variants as unavailable
        await cursor.executemany(
            '''UPDATE productVariants
               SET isAvailable = 0
               WHERE barcode = ?''',
            [(variant['barcode'],) for variant in variant_data]
        )

        # Commit the changes
        await conn.commit()

        logging.info(f"Sending payload to IMS: {json.dumps(payload, indent=4)}")
        return {
            'message': f"Order {orderID} marked as 'Shipped' and variants sent to IMS successfully.",
            'imsResponse': ims_response
        }

    except Exception as e:
        logging.error(f"Error shipping order: {e}")
        raise HTTPException(status_code=500, detail=f"Error shipping order: {e}")
    finally:
        if conn:
            await conn.close()


async def send_to_ims_api_with_retries(url, payload, retries=3, delay=2):
    for attempt in range(retries):
        try:
            logging.info(f"Attempt {attempt + 1} to send payload to IMS: {json.dumps(payload)}")
            async with ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    response_body = await response.text()
                    logging.info(f"IMS response (status: {response.status}): {response_body}")
                    if response.status == 200:
                        return await response.json()
                    else:
                        logging.error(f"IMS API returned non-200 status: {response.status}")
        except Exception as e:
            logging.error(f"Attempt {attempt + 1} failed: {e}")
        await asyncio.sleep(delay)
    raise HTTPException(status_code=500, detail="Failed to send data to IMS after multiple attempts.")

@router.get('/vms/orders/shipped')
async def get_shipped_orders():
    conn = None
    try:
        conn = await database.get_db_connection()
        cursor = await conn.cursor()

        # fetch all orders with status "Shipped"
        await cursor.execute(
            '''
            select orderID, orderDate, statusDate, customerID
            from purchaseOrders 
            where orderStatus = "Shipped"'''
        ),
        orders = await cursor.fetchall()

        # if no orders found, return an empty list
        if not orders:
            return {"message": "No shipped orders found", "orders": []}
        
        #format the results
        result = [
            {
                "orderID": order[0],
                "orderDate": order[1],
                "statusDate": order[2],
                "customerID": order[3]
            }
            for order in orders
        ]

        return {"message": "Shipped orders retrieved successfully", "orders": result}
    
    except Exception as e:
        logging.error(f"Error fetching shipped orders: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch shipped orders")
    finally: 
        if conn: 
            await conn.close()

@router.post('/vms/orders/update-status')
async def update_order_status(order_update: OrderUpdate):
    order_id = order_update.orderID
    order_status = order_update.orderStatus
    conn = None

    try:
        conn = await database.get_db_connection()
        cursor = await conn.cursor()

        # validate order existence in VMS
        await cursor.execute(
            '''select orderStatus 
            from purchaseOrders 
            where orderID = ?''',
            (order_id,)
        )
        existing_order = await cursor.fetchone()

        if not existing_order:
            raise HTTPException(status_code=404, detail="Order not found.")
        
        # log the current status for debugging
        logging.info(f"Current order status: {existing_order[0]}")

        # check if the status update is valid
        if existing_order[0] == order_status:
            return {"message": "Order status is already up-to-date."}
        
        # update the order status
        await cursor.execute(
            '''
            update purchaseOrders
            set orderStatus = ?, statusDate = getdate()
            where orderID = ?''',
            (order_status, order_id)
        )
        await conn.commit()

        logging.info(f"Order {order_id} status updated to {order_status}")
        return {"message": f"Order {order_id} status updated to {order_status}"}
    
    except Exception as e:
        logging.error(f"Error updating order status: {e}")
        raise HTTPException(status_code=500, detail="Failed to update order status.")
    finally:
        if conn:
            await conn.close()
