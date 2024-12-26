from fastapi import * 
from pydantic import BaseModel
import database
import random
import string
from typing import Optional
from routers.auth import get_current_active_user

# function to generate barcode
def generate_barcode():
    characters = string.ascii_uppercase + string.digits
    barcode = ''.join(random.choices(characters, k=13))
    return barcode

# function to generate sku
def generate_sku():
    characters = string.ascii_uppercase + string.digits
    sku = ''.join(random.choices(characters, k=8))
    return sku

router = APIRouter(dependencies=[Depends(get_current_active_user)])

# pydantic model for products 
class Product(BaseModel):
    productName: str
    productDescription: Optional[str] = None
    size: str
    color: str
    category: str
    unitPrice: float
    minStockLevel: int = 0
    maxStockLevel: int = 0
    quantity: int # number of variants to addd
    quantity: int =1 # number of variants to addd

# pydantic model for adding quantities to an existing product
class AddQuantity(BaseModel):
    productName: str
    size: str
    category: str
    quantity: int
    

class ProductVariant(BaseModel):
    productName: str
    barcode: str
    productCode: str
    productDescription: str
    size: str
    color: str
    unitPrice: float
    minStockLevel: int
    maxStockLevel: int
    isDamaged: bool = False 
    isWrongItem: bool = False
    isReturned: bool = False

@router.post('/products')
async def add_product(product: Product, is_new_product: bool = True):
    conn = await database.get_db_connection()
    cursor = await conn.cursor()
    try:
        # Check if a product with the same productName exists
        await cursor.execute('''
            select productID, productName, productDescription, size, color, category, unitPrice, 
            minStockLevel, maxStockLevel from Products where productName = ? and isActive = 1
        ''', product.productName)

        existing_product = await cursor.fetchone()

        if existing_product:
            # Compare the existing product's fields with the new product's fields
            if (existing_product[1] == product.productName and 
                existing_product[2] == product.productDescription and
                existing_product[3] == product.size and
                existing_product[4] == product.color and
                existing_product[5] == product.category and
                existing_product[6] == product.unitPrice and
                existing_product[7] == product.minStockLevel and
                existing_product[8] == product.maxStockLevel):
                # If all fields match, return a message indicating product is already available
                return {'message': f'Product "{product.productName}" is already available. You can add more quantity to the existing product.'}
            else:
                # If any field differs, treat it as a new product
                await cursor.execute(''' 
                    insert into Products (
                        productName, productDescription, size, color, category, 
                        unitPrice, minStockLevel, maxStockLevel)
                    values (?, ?, ?, ?, ?, ?, ?, ?)
                ''', product.productName,
                     product.productDescription,
                     product.size,
                     product.color,
                     product.category,
                     product.unitPrice,
                     product.minStockLevel,
                     product.maxStockLevel)
                await conn.commit()

                # Get the new productID
                await cursor.execute("select IDENT_CURRENT('Products')")
                product_id_row = await cursor.fetchone()
                product_id = product_id_row[0] if product_id_row else None

                if not product_id:
                    raise HTTPException(status_code=500, detail='Failed to retrieve productID after insertion')

                variants_data = [(
                    generate_barcode(),
                    generate_sku(),
                    product_id)
                    for _ in range(product.quantity)
                ]
                await cursor.executemany(
                    ''' insert into ProductVariants (barcode, productCode, productID)
                    values (?, ?, ?)
                    ''', variants_data
                )
                await conn.commit()

                return {'message': f'New Product "{product.productName}" added with {product.quantity} variants.'}

        else:
            # If the product does not exist, insert a new product
            await cursor.execute(''' 
                insert into Products (
                    productName, productDescription, size, color, category, 
                    unitPrice, minStockLevel, maxStockLevel)
                values (?, ?, ?, ?, ?, ?, ?, ?)
            ''', product.productName,
                 product.productDescription,
                 product.size,
                 product.color,
                 product.category,
                 product.unitPrice,
                 product.minStockLevel,
                 product.maxStockLevel)
            await conn.commit()

            # Get the new productID
            await cursor.execute("select IDENT_CURRENT('Products')")
            product_id_row = await cursor.fetchone()
            product_id = product_id_row[0] if product_id_row else None

            if not product_id:
                raise HTTPException(status_code=500, detail='Failed to retrieve productID after insertion')

            variants_data = [(
                generate_barcode(),
                generate_sku(),
                product_id)
                for _ in range(product.quantity)
            ]
            await cursor.executemany(
                ''' insert into ProductVariants (barcode, productCode, productID)
                values (?, ?, ?)
                ''', variants_data
            )
            await conn.commit()

            return {'message': f'New Product "{product.productName}" added with {product.quantity} variants.'}

    
        # get the last inserted productID
        await cursor.execute("select IDENT_CURRENT('Products')")
        product_id_row = await cursor.fetchone()
        product_id = product_id_row[0] if product_id_row else None

        if not product_id:
            raise HTTPException(status_code=500, detail='Failed to retrieve productID after insertion')

        # insert multiple variants/quantity into productVariants table
        variants_data= [(
                    generate_barcode(),
                    generate_sku(),
                    product_id )
                 for _ in range(product.quantity)
                 ]
        
        await cursor.executemany(
            ''' insert into ProductVariants (barcode, productCode, productID)
            values (?, ?, ?);''',
            variants_data
        )
        await conn.commit()

        return{'message': f'Product {product.productName} added with {product.quantity} variants.'}
    
    except Exception as e:
        await conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        await conn.close()

# add quantities to an existing products
@router.post('/products/add-quantity')
async def add_product_quantity(product: AddQuantity):
    conn = await database.get_db_connection()
    cursor = await conn.cursor()

    try:
        await cursor.execute(
            ''' select productID
            from Products
            where productName = ? and size = ? and category = ? and 
            isActive = 1''',
            product.productName, product.size, product.category
        )
        product_row = await cursor.fetchone()

        if not product_row:
            raise HTTPException(status_code=404, detail='Product not found.')

        product_id = product_row[0]

        variants_data= [(
                    generate_barcode(),
                    generate_sku(),
                    product_id )
                 for _ in range(product.quantity)
                 ]
        await cursor.executemany(
                    '''insert into ProductVariants (barcode, productCode, productID)
                    values (?, ?, ?)''',
                    variants_data
                )
        await conn.commit()
        return{'message': f'{product.quantity} quantities of {product.productName} added successfully.'}
    except Exception as e:
        await conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.close()
    
# get all productss 
@router.get("/products")
async def get_products():
    conn = await database.get_db_connection()
    try: 
        async with conn.cursor() as cursor:
            await cursor.execute('''
select p.productName, p.productDescription,
p.size, p.color, p.unitPrice, 
count(pv.variantID) as 'available quantity'
from products as p
left join ProductVariants as pv
on p.productID = pv.productID
where p.isActive = 1 and pv.isAvailable =1
group by p.productName, p.productDescription, p.size, p.color, p.unitPrice
''')
            products = await cursor.fetchall()
            # map column names to row values
            return [dict(zip([column[0] for column in cursor.description], row)) for row in products]
    finally: 
        await conn.close()

# get one product
@router.get('/products/{product_id}')
async def get_product(product_id: int):
    conn = await database.get_db_connection()
    cursor = await conn.cursor()
    try:
        await cursor.execute('''select p.productName, p.productDescription,
            p.size, p.color, p.unitPrice,
            p.size, p.color, p.unitPrice, 
            p.minStockLevel, p.maxStockLevel,
            count(pv.variantID) as 'available quantity'
            from products as p
            left join ProductVariants as pv
            on p.productID = pv.productID
            where p.isActive = 1 and pv.isAvailable =1
            and p.productID = ?
            group by p.productName, p.productDescription, p.size, p.color, p.unitPrice, p.minStockLevel, p.maxStockLevel''', product_id)
        #group by p.productName, p.productDescription, p.size, p.color, p.unitPrice, ''', product_id)
        product = await cursor.fetchone()
        if not product:
            raise HTTPException(status_code=404, detail='product not found')
        return dict(zip([column[0] for column in cursor.description], product))
    finally:
        await conn.close()

# get all product variants 
@router.get("/product/variants")
async def get_product_variants():
    conn = await database.get_db_connection()
    try: 
        async with conn.cursor() as cursor:
            await cursor.execute('''
select p.productName, pv.barcode, pv.productCode, 
p.productDescription, p.size, p.color, p.unitPrice, 
p.minStockLevel, p.maxStockLevel
from Products as p
full outer join ProductVariants as pv
on p.productID = pv.productID
where p.isActive = 1 and pv.isAvailable = 1;''')
            products = await cursor.fetchall()
            # map column names to row values
            return [dict(zip([column[0] for column in cursor.description], row)) for row in products]
    finally: 
        await conn.close()

# get one product variant
@router.get('/products/variant/{variant_id}', response_model=ProductVariant)
async def get_product(variant_id: int):
    conn = await database.get_db_connection()
    cursor = await conn.cursor()
    try:
        await cursor.execute('''select p.productName, pv.barcode, pv.productCode, 
p.productDescription, p.size, p.color, p.unitPrice,
p.minStockLevel, p.maxStockLevel
from Products as p
full outer join ProductVariants as pv
on p.productID = pv.productID
where p.isActive = 1 and pv.isAvailable = 1
and pv.variantID = ?''', variant_id)
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail='product variant not found')
        
        product_variant = ProductVariant(
            productName=row[0],
            barcode=row[1],
            productCode=row[2],
            productDescription=row[3],
            size=row[4],
            color=row[5],
            unitPrice=row[6],
            minStockLevel=row[7],
            maxStockLevel=row[8]
        )
        return product_variant
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.close()


# update a product
@router.put('/products/{product_id}')
async def update_product(product_id: int, product: Product):
    conn = await database.get_db_connection()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute(
            '''
update Products
set productName = ?, productDescription = ?, size = ?, color = ?, category = ?, unitPrice = ?, 
minStockLevel = ?, maxStockLevel = ?
where productID = ? ''',
            product.productName,
            product.productDescription,
            product.size,
            product.color,
            product.category,
            product.unitPrice,
            product.minStockLevel,
            product.maxStockLevel,
            product_id,
        )
            await conn.commit()
            return{'message': 'product updated successfully!'}
    except Exception as e:
        await conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.close()

# delete a product
@router.delete('/products/{product_id}')
async def delete_product(product_id: int):
    conn = await database.get_db_connection()
    try:
        async with conn.cursor() as cursor:
            #await cursor.execute('''update products
                       #set isDeleted=1
            await cursor.execute('''update ProductVariant
                       set isActive=0
                       where productID = ?''', product_id)
            await conn.commit()
            return {'message': 'product deleted successfully'}
    except Exception as e:
        await conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.close()

# delete a product variant
@router.delete('/products/variant/{variant_id}')
async def delete_product(variant_id: int):
    conn = await database.get_db_connection()
    try:
        async with conn.cursor() as cursor:
            await cursor.execute('''update products
                       set isAvailable = 0
                       where variantID = ?''', variant_id)
            await conn.commit()
            return {'message': 'Product variant deleted successfully'}
    except Exception as e:
        await conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await conn.close()