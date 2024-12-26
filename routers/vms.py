# from fastapi import FastAPI, HTTPException
# from pydantic import BaseModel
# import database

# app = FastAPI()

# # Pydantic model for purchase order
# class PurchaseOrder(BaseModel):
#     orderID: int
#     productID: int
#     productName: str
#     productDescription: str
#     size: str
#     color: str
#     category: str
#     quantity: int
#     warehouseID: int
#     vendorID: int
#     vendorName: str
#     orderDate: str
#     expectedDate: str

# @app.post("/orders")
# async def receive_order(order: PurchaseOrder):
#     try:
#         # Connect to the database
#         conn = await database.get_db_connection()
#         cursor = await conn.cursor()

#         # Validate vendor and warehouse
#         await cursor.execute(
#             '''
#             SELECT vendorID 
#             FROM Vendors 
#             WHERE vendorID = ? AND isActive = 1
#             ''',
#             (order.vendorID,)
#         )
#         vendor = await cursor.fetchone()
#         if not vendor:
#             raise HTTPException(status_code=404, detail="Vendor not found or inactive.")

#         await cursor.execute(
#             '''
#             SELECT warehouseID 
#             FROM Warehouses 
#             WHERE warehouseID = ?
#             ''',
#             (order.warehouseID,)
#         )
#         warehouse = await cursor.fetchone()
#         if not warehouse:
#             raise HTTPException(status_code=404, detail="Warehouse not found.")

#         # Log the purchase order details into the database
#         await cursor.execute(
#             '''
#             INSERT INTO PurchaseOrders (orderDate, orderStatus, statusDate, vendorID)
#             OUTPUT INSERTED.orderID
#             VALUES (?, ?, ?, ?)
#             ''',
#             (order.orderDate, "Received", datetime.now(), order.vendorID)
#         )
#         inserted_order = await cursor.fetchone()
#         orderID = inserted_order[0] if inserted_order else None

#         if not orderID:
#             raise HTTPException(status_code=500, detail="Failed to log purchase order.")

#         await cursor.execute(
#             '''
#             INSERT INTO PurchaseOrderDetails (orderQuantity, expectedDate, warehouseID, orderID)
#             VALUES (?, ?, ?, ?)
#             ''',
#             (order.quantity, order.expectedDate, order.warehouseID, orderID)
#         )

#         await conn.commit()

#         return {"message": "Purchase order received and logged successfully.", "orderID": orderID}

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error processing purchase order: {e}")
#     finally:
#         await conn.close()

# # Health check endpoint
# @app.get("/health")
# async def health_check():
#     return {"message": "VMS is running."}



# SAMPLE POST METHOD TO RECEIVE ORDERS FROM IMS
from fastapi import FastAPI, HTTPException, APIRouter

router = APIRouter()

@router.post("/orders")
async def create_order(payload: dict):
    print("Received Payload:", payload)
    if "productID" not in payload or "quantity" not in payload:
        raise HTTPException(status_code=400, detail="Invalid payload")
    return {"message": "Order received successfully", "payload": payload}

