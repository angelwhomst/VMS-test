# from fastapi import APIRouter, HTTPException

# router = APIRouter()

# @router.post("/order")
# async def receive_order(order: dict):
#     """
#     Endpoint to receive purchase orders from the IMS.
#     """
#     try:
#         # Log the order (extend to save it in a database or process it)
#         print("Received order:", order)
        
#         # Respond with a success message
#         return {"message": "Order received successfully!", "order_details": order}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error processing order: {str(e)}")
from fastapi import APIRouter, Depends, HTTPException
from routers.auth import get_current_active_user
from pydantic import BaseModel
import aioodbc
import database
from datetime import datetime

# Initialize Router
router = APIRouter(dependencies=[Depends(get_current_active_user)])  # All routes in this router are now secured

# Vendor Model
class Vendor(BaseModel):
    vendorName: str
    contactNumber: str
    contactEmail: str = None
    building: str = None
    street: str = None
    barangay: str = None
    city: str = None
    country: str = None
    zipcode: str = None
    IS_ACTIVE: bool = True  # Boolean type for active status


# Create a Vendor
@router.post("/")
async def create_vendor(vendor: Vendor, db=Depends(database.get_db_connection)):
    """
    Add a new vendor to the database.
    """
    try:
        cursor = await db.cursor()
        try:
            created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # Get current timestamp
            await cursor.execute(
                """
                INSERT INTO Vendors (VendorName, ContactNumber, ContactEmail, Building, Street, Barangay, City, Country, Zipcode, IS_ACTIVE, CreatedAt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (vendor.vendorName, vendor.contactNumber, vendor.contactEmail, vendor.building, vendor.street,
                 vendor.barangay, vendor.city, vendor.country, vendor.zipcode, vendor.IS_ACTIVE, created_at),
            )
            await db.commit()
            return {"message": "Vendor created successfully"}
        finally:
            await cursor.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating vendor: {str(e)}")


# List All Active Vendors
@router.get("/")
async def list_vendors(db=Depends(database.get_db_connection)):
    """
    Retrieve all active vendors (exclude soft-deleted).
    """
    try:
        cursor = await db.cursor()
        try:
            await cursor.execute("SELECT * FROM Vendors WHERE IS_ACTIVE = 1")
            rows = await cursor.fetchall()
            if not rows:
                raise HTTPException(status_code=404, detail="No active vendors found")
        finally:
            await cursor.close()

        return [
            {
                "VendorID": row[0],
                "VendorName": row[1],
                "ContactNumber": row[2],
                "ContactEmail": row[3],
                "Building": row[4],
                "Street": row[5],
                "Barangay": row[6],
                "City": row[7],
                "Country": row[8],
                "Zipcode": row[9],
                "CreatedAt": row[10],
                "UpdatedAt": row[11],
            }
            for row in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch vendors: {str(e)}")


# Get Vendor by ID
@router.get("/{vendor_id}")
async def get_vendor(vendor_id: int, include_inactive: bool = False, db=Depends(database.get_db_connection)):
    """
    Retrieve details of a specific vendor by ID.
    Optionally include soft-deleted vendors by setting `include_inactive` to True.
    """
    try:
        cursor = await db.cursor()
        try:
            query = "SELECT * FROM Vendors WHERE VendorID = ?"
            params = [vendor_id]

            if not include_inactive:
                query += " AND IS_ACTIVE = 1"

            await cursor.execute(query, params)
            row = await cursor.fetchone()
        finally:
            await cursor.close()

        if row:
            return {
                "VendorID": row[0],
                "VendorName": row[1],
                "ContactNumber": row[2],
                "ContactEmail": row[3],
                "Building": row[4],
                "Street": row[5],
                "Barangay": row[6],
                "City": row[7],
                "Country": row[8],
                "Zipcode": row[9],
                "CreatedAt": row[10],
                "UpdatedAt": row[11],
            }
        else:
            raise HTTPException(status_code=404, detail="Vendor not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching vendor: {str(e)}")


# Update a Vendor
@router.put("/{vendor_id}")
async def update_vendor(vendor_id: int, vendor: Vendor, db=Depends(database.get_db_connection)):
    """
    Update an existing vendor by ID.
    """
    try:
        cursor = await db.cursor()
        try:
            updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # Get current timestamp
            # Update vendor details
            await cursor.execute(
                """
                UPDATE Vendors
                SET VendorName = ?, ContactNumber = ?, ContactEmail = ?, Building = ?, Street = ?, Barangay = ?, City = ?, Country = ?, Zipcode = ?, UpdatedAt = ?
                WHERE VendorID = ? AND IS_ACTIVE = 1
                """,
                (vendor.vendorName, vendor.contactNumber, vendor.contactEmail, vendor.building, vendor.street,
                 vendor.barangay, vendor.city, vendor.country, vendor.zipcode, updated_at, vendor_id),
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Vendor not found or already inactive")
            await db.commit()
            return {"message": "Vendor updated successfully"}
        finally:
            await cursor.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating vendor: {str(e)}")


# Soft Delete a Vendor
@router.delete("/{vendor_id}")
async def delete_vendor(vendor_id: int, db=Depends(database.get_db_connection)):
    """
    Soft delete a vendor by setting IS_ACTIVE to False (0).
    """
    try:
        cursor = await db.cursor()
        try:
            updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # Get current timestamp
            await cursor.execute(
                """
                UPDATE Vendors
                SET IS_ACTIVE = 0, UpdatedAt = ?
                WHERE VendorID = ? AND IS_ACTIVE = 1
                """,
                (updated_at, vendor_id),
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Vendor not found or already inactive")
            await db.commit()
            return {"message": "Vendor soft-deleted successfully"}
        finally:
            await cursor.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to soft delete vendor")


# Reactivate a Soft-Deleted Vendor
@router.put("/{vendor_id}/reactivate")
async def reactivate_vendor(vendor_id: int, db=Depends(database.get_db_connection)):
    """
    Reactivate a soft-deleted vendor by setting IS_ACTIVE to True (1).
    """
    try:
        cursor = await db.cursor()
        try:
            updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # Get current timestamp
            await cursor.execute(
                """
                UPDATE Vendors
                SET IS_ACTIVE = 1, UpdatedAt = ?
                WHERE VendorID = ? AND IS_ACTIVE = 0
                """,
                (updated_at, vendor_id),
            )
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Vendor not found or already active")
            await db.commit()
            return {"message": "Vendor reactivated successfully"}
        finally:
            await cursor.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to reactivate vendor")