"""
Banya Bot - Telegram bot for booking saunas and bath masters.

Usage:
    python main.py bot     - Run only the Telegram bot
    python main.py api     - Run only the API server
    python main.py all     - Run both bot and API server
    python main.py seed    - Seed database with demo data
"""

import asyncio
import sys
import uvicorn
from pathlib import Path


async def run_bot():
    """Run the Telegram bot."""
    from src.bot import bot, dp, setup_bot
    from src.database import init_db

    # Initialize database
    await init_db()

    # Auto-seed database if empty
    await auto_seed_if_empty()

    # Setup bot handlers
    setup_bot()

    # Start polling
    print("🤖 Starting Telegram bot...")
    await dp.start_polling(bot)


async def auto_seed_if_empty():
    """Automatically seed database if it's empty."""
    from sqlalchemy import select
    from src.database import async_session
    from src.database.models import City

    async with async_session() as session:
        result = await session.execute(select(City))
        if not result.scalars().first():
            print("📦 Database is empty, seeding with demo data...")
            await seed_database()
        else:
            print("✅ Database already has data")


def run_api():
    """Run the API server."""
    from src.config import get_settings
    from src.api import create_app

    settings = get_settings()
    app = create_app()

    print(f"🌐 Starting API server on {settings.api_host}:{settings.api_port}...")
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
    )


async def run_all():
    """Run both bot and API server."""
    import threading
    from src.database import init_db

    # Initialize database
    await init_db()

    # Run API in a separate thread
    api_thread = threading.Thread(target=run_api, daemon=True)
    api_thread.start()

    # Run bot in main thread
    await run_bot()


async def seed_database():
    """Seed database with demo data."""
    from decimal import Decimal
    from src.database import init_db, async_session
    from src.database.models import City, Banya, BathMaster, User, UserRole, BanyaPhoto

    print("🌱 Seeding database...")

    await init_db()

    async with async_session() as session:
        # Check if data already exists
        from sqlalchemy import select

        result = await session.execute(select(City))
        if result.scalars().first():
            print("⚠️ Database already seeded!")
            return

        # Create cities
        cities = [
            City(name="Москва", region="Московская область"),
            City(name="Санкт-Петербург", region="Ленинградская область"),
            City(name="Новосибирск", region="Новосибирская область"),
            City(name="Екатеринбург", region="Свердловская область"),
            City(name="Казань", region="Республика Татарстан"),
        ]
        session.add_all(cities)
        await session.flush()

        # Create demo owner
        owner = User(
            telegram_id=123456789,
            username="banya_owner",
            first_name="Владелец",
            last_name="Бани",
            role=UserRole.BANYA_OWNER,
        )
        session.add(owner)
        await session.flush()

        # Create banyas
        banyas_data = [
            {
                "name": "Русские Бани на Пресне",
                "description": "Настоящая русская баня с вековыми традициями. Профессиональные парильщики, дубовые веники.",
                "address": "ул. Пресненский Вал, 15",
                "city_id": cities[0].id,
                "price_per_hour": Decimal("3500"),
                "min_hours": 2,
                "max_guests": 8,
                "has_russian_banya": True,
                "has_pool": True,
                "has_cold_plunge": True,
                "has_rest_room": True,
                "has_parking": True,
                "provides_veniks": True,
                "provides_towels": True,
                "provides_robes": True,
                "rating": 4.8,
                "rating_count": 156,
            },
            {
                "name": "SPA Хаммам Восток",
                "description": "Аутентичный турецкий хаммам с мраморными плитами и профессиональным скрабированием.",
                "address": "Арбат, 25с1",
                "city_id": cities[0].id,
                "price_per_hour": Decimal("4500"),
                "min_hours": 2,
                "max_guests": 6,
                "has_hammam": True,
                "has_jacuzzi": True,
                "has_rest_room": True,
                "provides_towels": True,
                "provides_robes": True,
                "provides_drinks": True,
                "rating": 4.9,
                "rating_count": 89,
            },
            {
                "name": "Финская Сауна Релакс",
                "description": "Классическая финская сауна с березовыми вениками и охлаждающим бассейном.",
                "address": "Невский проспект, 100",
                "city_id": cities[1].id,
                "price_per_hour": Decimal("2800"),
                "min_hours": 2,
                "max_guests": 10,
                "has_finnish_sauna": True,
                "has_pool": True,
                "has_billiards": True,
                "has_karaoke": True,
                "has_parking": True,
                "provides_veniks": True,
                "provides_towels": True,
                "rating": 4.6,
                "rating_count": 234,
            },
            {
                "name": "Баня Купеческая",
                "description": "Традиционная русская баня в купеческом стиле. Ледяная купель, берёзовые и дубовые веники.",
                "address": "ул. Ленина, 45",
                "city_id": cities[1].id,
                "price_per_hour": Decimal("3200"),
                "min_hours": 3,
                "max_guests": 12,
                "has_russian_banya": True,
                "has_cold_plunge": True,
                "has_rest_room": True,
                "has_bbq": True,
                "has_parking": True,
                "provides_veniks": True,
                "provides_towels": True,
                "provides_food": True,
                "provides_drinks": True,
                "rating": 4.7,
                "rating_count": 178,
            },
            {
                "name": "Сибирские Бани",
                "description": "Настоящий сибирский пар! Кедровая бочка, травяные чаи, профессиональные парильщики.",
                "address": "пр. Маркса, 12",
                "city_id": cities[2].id,
                "price_per_hour": Decimal("2500"),
                "min_hours": 2,
                "max_guests": 8,
                "has_russian_banya": True,
                "has_infrared_sauna": True,
                "has_cold_plunge": True,
                "has_rest_room": True,
                "provides_veniks": True,
                "provides_towels": True,
                "provides_drinks": True,
                "rating": 4.5,
                "rating_count": 112,
            },
            {
                "name": "Уральские Термы",
                "description": "Комплекс с русской баней, финской сауной и хаммамом. Всё в одном месте!",
                "address": "ул. Малышева, 78",
                "city_id": cities[3].id,
                "price_per_hour": Decimal("4000"),
                "min_hours": 2,
                "max_guests": 15,
                "has_russian_banya": True,
                "has_finnish_sauna": True,
                "has_hammam": True,
                "has_pool": True,
                "has_jacuzzi": True,
                "has_salt_room": True,
                "has_rest_room": True,
                "has_parking": True,
                "provides_veniks": True,
                "provides_towels": True,
                "provides_robes": True,
                "provides_food": True,
                "provides_drinks": True,
                "rating": 4.9,
                "rating_count": 267,
            },
            {
                "name": "Татарская Баня",
                "description": "Уникальное сочетание русских и восточных традиций. Травяные веники, медовый массаж.",
                "address": "ул. Баумана, 33",
                "city_id": cities[4].id,
                "price_per_hour": Decimal("3000"),
                "min_hours": 2,
                "max_guests": 10,
                "has_russian_banya": True,
                "has_hammam": True,
                "has_rest_room": True,
                "has_parking": True,
                "provides_veniks": True,
                "provides_towels": True,
                "provides_robes": True,
                "provides_food": True,
                "rating": 4.7,
                "rating_count": 145,
            },
        ]

        for banya_data in banyas_data:
            banya = Banya(owner_id=owner.id, **banya_data)
            session.add(banya)

        await session.flush()

        # Create bath masters
        masters_users = [
            User(
                telegram_id=111111111,
                username="master_ivan",
                first_name="Иван",
                last_name="Парильщиков",
                role=UserRole.BATH_MASTER,
            ),
            User(
                telegram_id=222222222,
                username="master_sergey",
                first_name="Сергей",
                last_name="Веников",
                role=UserRole.BATH_MASTER,
            ),
            User(
                telegram_id=333333333,
                username="master_ahmed",
                first_name="Ахмед",
                last_name="Хаммамов",
                role=UserRole.BATH_MASTER,
            ),
        ]
        session.add_all(masters_users)
        await session.flush()

        masters = [
            BathMaster(
                user_id=masters_users[0].id,
                bio="15 лет опыта в русской бане. Мастер дубового и берёзового веника. Выезжаю на дом!",
                experience_years=15,
                price_per_session=Decimal("3000"),
                session_duration_minutes=60,
                specializes_russian=True,
                specializes_massage=True,
                can_visit_home=True,
                home_visit_price=Decimal("5000"),
                rating=4.9,
                rating_count=89,
            ),
            BathMaster(
                user_id=masters_users[1].id,
                bio="Мастер финской сауны и русской бани. Специализация - ароматерапия.",
                experience_years=8,
                price_per_session=Decimal("2500"),
                session_duration_minutes=60,
                specializes_russian=True,
                specializes_finnish=True,
                specializes_aromatherapy=True,
                can_visit_home=False,
                rating=4.7,
                rating_count=56,
            ),
            BathMaster(
                user_id=masters_users[2].id,
                bio="Профессиональный мастер хаммама. Обучался в Турции. Возможен выезд.",
                experience_years=10,
                price_per_session=Decimal("3500"),
                session_duration_minutes=90,
                specializes_hammam=True,
                specializes_scrub=True,
                specializes_massage=True,
                can_visit_home=True,
                home_visit_price=Decimal("6000"),
                rating=4.8,
                rating_count=72,
            ),
        ]
        session.add_all(masters)
        await session.flush()

        # Get all banyas to link masters
        from sqlalchemy import select as sa_select
        banyas_result = await session.execute(sa_select(Banya))
        all_banyas = banyas_result.scalars().all()

        # Link masters to banyas (create associations)
        from src.database.models import BanyaBathMaster

        # Master 0 (Иван) works in Moscow banyas (first 2)
        for banya in all_banyas[:2]:
            session.add(BanyaBathMaster(banya_id=banya.id, bath_master_id=masters[0].id))

        # Master 1 (Сергей) works in SPb banyas (3-4)
        for banya in all_banyas[2:4]:
            session.add(BanyaBathMaster(banya_id=banya.id, bath_master_id=masters[1].id))

        # Master 2 (Ахмед) works in multiple cities (hammam specialist)
        for banya in all_banyas:
            if banya.has_hammam:
                session.add(BanyaBathMaster(banya_id=banya.id, bath_master_id=masters[2].id))

        await session.commit()

        print("✅ Database seeded successfully!")
        print(f"   - {len(cities)} cities")
        print(f"   - {len(banyas_data)} banyas")
        print(f"   - {len(masters)} bath masters")
        print(f"   - Masters linked to banyas")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "bot":
        asyncio.run(run_bot())
    elif command == "api":
        run_api()
    elif command == "all":
        asyncio.run(run_all())
    elif command == "seed":
        asyncio.run(seed_database())
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
