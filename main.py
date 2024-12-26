from fastapi import FastAPI  
import uvicorn  

# Import routers  
from routers import products, auth, orderdetails, vendor, orders, vms

# Initialize the FastAPI application  
app = FastAPI()  

# Include routers  
app.include_router(orderdetails.router, prefix='/vms', tags=['Order details'])
app.include_router(orders.router, prefix='/orders', tags=['Orders']) 
app.include_router(vms.router, prefix='/test', tags=['Receive Orders TEST'])  
app.include_router(auth.router, prefix='/auth', tags=['Authentication'])  
app.include_router(products.router, prefix='/products', tags=['Product Management'])  
# app.include_router(vendor.router, prefix='/vendors', tags=['Vendor Management'])  

if __name__ == "__main__":  
    uvicorn.run("main:app", port=8001, host='127.0.0.1', reload=True)