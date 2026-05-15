from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Numeric, Boolean, JSON, ForeignKey, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional
from sqlalchemy import extract

# 1. Настройка базы данных
DATABASE_URL = "postgresql://neondb_owner:npg_Z6wpVujMoK5f@ep-damp-breeze-alfac21w-pooler.c-3.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. Модели таблиц SQLAlchemy
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100))
    email = Column(String(150), unique=True, index=True)
    password = Column(String(255))
    role = Column(String(50), default="user")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255))
    category = Column(String(100))
    price = Column(Numeric(10, 2))
    original_price = Column(Numeric(10, 2), nullable=True)
    image = Column(String)
    description = Column(String)
    specifications = Column(JSON, default=[])
    featured = Column(Boolean, default=False)
    stock = Column(Integer, default=0)

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    product_name = Column(String(255))
    quantity = Column(Integer)
    total_price = Column(Numeric(10, 2))
    address = Column(String)
    status = Column(String(50), default="Новый")
    created_at = Column(DateTime, default=datetime.utcnow)

# Создание таблиц
Base.metadata.create_all(bind=engine)

# 3. Pydantic модели
class UserRegisterRequest(BaseModel):
    username: str
    email: str
    password: str

class UserLoginRequest(BaseModel):
    email: str
    password: str

class OrderCreateRequest(BaseModel):
    user_id: int
    product_name: str
    quantity: int
    total_price: float
    address: str

class ProductAdminRequest(BaseModel):
    name: str
    category: str
    price: float
    original_price: Optional[float] = None
    image: str
    description: str
    specifications: Optional[list] = None
    featured: bool = False
    stock: int = 0

class OrderStatusUpdateRequest(BaseModel):
    status: str    

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- АВТОРИЗАЦИЯ ---
@app.post("/api/register")
def register(user_data: UserRegisterRequest, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Этот email уже зарегистрирован")
    new_user = User(username=user_data.username, email=user_data.email, password=user_data.password)
    db.add(new_user)
    db.commit()
    return {"status": "success", "message": "Пользователь успешно создан"}

@app.post("/api/login")
def login(user_data: UserLoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == user_data.email, User.password == user_data.password).first()
    if not user:
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    return {"status": "success", "id": user.id, "username": user.username, "email": user.email, "role": user.role}

# --- ТОВАРЫ ---
@app.get("/api/products")
def get_products(db: Session = Depends(get_db)):
    try:
        items = db.query(Product).order_by(Product.id).all()
        return [
            {
                "id": item.id,
                "name": item.name,
                "category": item.category,
                "price": float(item.price),
                "original_price": float(item.original_price) if item.original_price else None,
                "image": item.image,
                "description": item.description,
                "featured": item.featured,
                "specifications": item.specifications if item.specifications else [],
                "stock": item.stock
            } for item in items
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка БД: {str(e)}")

# --- ЗАКАЗЫ (Добавленные методы) ---

@app.post("/api/orders")
def create_order(item: OrderCreateRequest, db: Session = Depends(get_db)):
    new_order = Order(
        user_id=item.user_id,
        product_name=item.product_name,
        quantity=item.quantity,
        total_price=item.total_price,
        address=item.address,
        status="Новый"
    )
    db.add(new_order)
    db.commit()
    return {"status": "success"}

@app.get("/api/orders/{user_id}")
def get_user_orders(user_id: int, db: Session = Depends(get_db)):
    orders = db.query(Order).filter(Order.user_id == user_id).order_by(Order.created_at.desc()).all()
    return [
        {
            "id": o.id,
            "product_name": o.product_name,
            "quantity": o.quantity,
            "total_price": float(o.total_price),
            "address": o.address,
            "status": o.status,
            "date": o.created_at.strftime("%d.%m.%Y")
        } for o in orders
    ]

# --- АДМИН-ПАНЕЛЬ ---
@app.get("/api/admin/stats")
def get_admin_stats(db: Session = Depends(get_db)):
    revenue = db.query(func.sum(Order.total_price)).scalar() or 0
    return {
        "products": db.query(Product).count(),
        "users": db.query(User).count(),
        "orders": db.query(Order).count(),
        "revenue": float(revenue)
    }

@app.get("/api/admin/users")
def get_all_users(db: Session = Depends(get_db)):
    # Добавляем .filter(User.role == "user"), чтобы исключить админов из списка
    users = db.query(User).filter(User.role == "user").all()
    
    result = []
    for u in users:
        order_count = db.query(Order).filter(Order.user_id == u.id).count()
        result.append({
            "id": u.id, 
            "name": u.username, 
            "email": u.email, 
            "created_date": u.created_at, 
            "orders": order_count
        })
    return result

@app.get("/api/admin/orders")
def get_admin_orders(db: Session = Depends(get_db)):
    orders = db.query(Order).order_by(Order.created_at.desc()).all()
    result = []
    for o in orders:
        user = db.query(User).filter(User.id == o.user_id).first()
        result.append({
            "id": o.id,
            "customer": user.username if user else "Удален",
            "date": o.created_at.strftime("%d.%m.%Y"),
            "amount": float(o.total_price),
            "status": o.status
        })
    return result

@app.post("/api/admin/products")
def add_product(item: ProductAdminRequest, db: Session = Depends(get_db)):
    new_p = Product(
        name=item.name,
        category=item.category,
        price=item.price,
        original_price=item.original_price,
        image=item.image,
        description=item.description,
        specifications=item.specifications,
        featured=item.featured,
        stock = item.stock
    )
    db.add(new_p)
    db.commit()
    return {"status": "success"}

@app.put("/api/admin/products/{p_id}")
def update_product(p_id: int, item: ProductAdminRequest, db: Session = Depends(get_db)):
    db_p = db.query(Product).filter(Product.id == p_id).first()
    if not db_p: raise HTTPException(status_code=404, detail="Товар не найден")
    
    db_p.name = item.name
    db_p.category = item.category
    db_p.price = item.price
    db_p.original_price = item.original_price
    db_p.image = item.image
    db_p.description = item.description
    db_p.specifications = item.specifications
    db_p.featured = item.featured
    db_p.stock = item.stock
    
    db.commit()
    return {"status": "success"}

@app.delete("/api/admin/products/{p_id}")
def delete_product(p_id: int, db: Session = Depends(get_db)):
    db_p = db.query(Product).filter(Product.id == p_id).first()
    if not db_p: raise HTTPException(status_code=404, detail="Товар не найден")
    db.delete(db_p)
    db.commit()
    return {"status": "success"}


@app.get("/api/admin/orders-stats")
def get_orders_stats(db: Session = Depends(get_db)):
    # Группируем заказы по месяцам и считаем их количество
    stats = db.query(
        extract('month', Order.created_at).label('month'),
        func.count(Order.id).label('count')
    ).group_by('month').order_by('month').all()
    
    # Список названий месяцев для сопоставления
    month_names = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", 
                   "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
    
    labels = []
    values = []
    
    for s in stats:
        # s.month возвращает число (1, 2, 3...), вычитаем 1 для индекса списка
        labels.append(month_names[int(s.month) - 1])
        values.append(s.count)
    
    return {"labels": labels, "values": values}


@app.patch("/api/admin/orders/{order_id}")
def update_order_status(order_id: int, data: OrderStatusUpdateRequest, db: Session = Depends(get_db)):
    # 1. Ищем заказ в базе
    db_order = db.query(Order).filter(Order.id == order_id).first()
    
    # 2. Если не нашли — отдаем 404
    if not db_order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    
    # 3. Обновляем статус
    db_order.status = data.status
    
    try:
        db.commit()
        db.refresh(db_order)
        return {"status": "success", "new_status": db_order.status}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при обновлении: {str(e)}")