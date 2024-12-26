from fastapi import Depends, APIRouter, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
import aioodbc
import database


# JWT Configuration
SECRET_KEY = "15882913506880857248f72d1dbc38dd7d2f8f352786563ef5f23dc60987c632"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Set password hashing mechanism
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

# FastAPI Router
router = APIRouter()


# Models for JWT token and user management
class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None


class User(BaseModel):
    username: str
    firstName: str | None = None
    lastName: str | None = None
    email: str | None = None
    userRole: str | None = None
    disabled: bool | None = None


class UserInDB(User):
    hashed_password: str


# Database helper to get a user from the DB
async def get_user_from_db(username: str):
    """Fetch user from DB."""
    try:
        conn = await database.get_db_connection()
        cursor = await conn.cursor()
        await cursor.execute(
            "SELECT username, userPassword, userRole, isDisabled, firstName, lastName FROM users WHERE username = ?", 
            (username,)
        )
        user_row = await cursor.fetchone()
        if user_row:
            return UserInDB(
                username=user_row[0],
                hashed_password=user_row[1],
                userRole=user_row[2],
                disabled=bool(user_row[3]),
                firstName=user_row[4],
                lastName=user_row[5],
            )
        return None
    except Exception as e:
        print(f"Error accessing database: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        await cursor.close()
        await conn.close()


# Create admin user on server startup
async def create_admin_user():
    """Check if admin user exists; if not, create one."""
    try:
        admin_user = await get_user_from_db('admin')
        if not admin_user:
            hashed_password = get_password_hash('admin123')
            conn = await database.get_db_connection()
            cursor = await conn.cursor()
            try:
                await cursor.execute(
                    "INSERT INTO users (username, userPassword, userRole, isDisabled, firstName, lastName) VALUES (?, ?, ?, ?, ?, ?)",
                    ('admin', hashed_password, 'admin', 0, 'Admin', 'User'),
                )
                await conn.commit()
                print("Admin user created successfully.")
            finally:
                await cursor.close()
                await conn.close()
        else:
            print("Admin already exists.")
    except Exception as e:
        print(f"Failed to create admin user: {e}")


# JWT Helper Functions
def get_password_hash(password: str) -> str:
    """Hashes a password."""
    return pwd_context.hash(password)


def verify_password(plain_password, hashed_password) -> bool:
    """Verifies that a plain password matches the hashed password."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Generates JWT token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# Authentication logic
async def authenticate_user(username: str, password: str):
    """Authenticate user using DB credentials."""
    user = await get_user_from_db(username)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


# Dependency: Validate JWT token and get user
async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Validate JWT token and get the current user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception

    user = await get_user_from_db(token_data.username)
    if user is None:
        raise credentials_exception

    return user


# Protect route with active user validation
async def get_current_active_user(current_user: UserInDB = Depends(get_current_user)):
    """Check if the user is active."""
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


# Login route
@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """Authenticate user and return JWT token on success."""
    user = await authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


# Route to fetch user details
@router.get("/users/me", response_model=User)
async def read_users_me(current_user: UserInDB = Depends(get_current_active_user)):
    """Return current user's profile."""
    return current_user


# Call `create_admin_user` at startup
@router.on_event('startup')
async def startup_event():
    await create_admin_user()


class Product(BaseModel):
    productName: str
    productDescription: str 
    color: str
    unitPrice: float
    category: str
    minStockLevel: int = 0
    maxStockLevel: int = 0
    quantity: int # number of variants to addd
    quantity: int =1 # number of variants to addd

class ProductInDB(Product):
    productID: int
    createdAt: str = None
    lastUpdated: str = None
    isActive: bool = True
class AddQuantity(BaseModel):
    productName: str
    quantity: int

class ProductVariant(BaseModel):
    barcode: str
    productCode: str
    isDamaged: bool = False
    isWrongItem: bool = False
    isReturned: bool = False
    productID: int  # Foreign key to Product
    isAvailable: bool = True  # Default to True (available)

class ProductVariantInDB(ProductVariant):
    variantID: int
# Vendor Model with is_active
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
    IS_ACTIVE: bool = True  # Default to True for active vendors
    isAvailable: bool = True

# PurchaseOrder Model

class PurchaseOrder(BaseModel):
    orderDate: datetime
    orderStatus: str
    statusDate: datetime
    vendorID: int  # Foreign key to vendor
    isActive: bool = True  # Default to True (active)




# PurchaseOrderDetail Model
class PurchaseOrderDetail(BaseModel):
    orderQuantity: int
    expectedDate: datetime
    actualDate: datetime = None
    productID: int  # Foreign key to product