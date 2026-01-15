"""Notification service for sending messages to booking participants."""

from typing import Optional
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.database import async_session, Booking, User, Banya, BathMaster
from src.database.models import BookingStatus, BookingType, CancelledBy


class NotificationService:
    """Service for sending notifications to booking participants."""

    def __init__(self, bot: Bot):
        self.bot = bot

    async def get_booking_with_relations(self, booking_id: int) -> Optional[Booking]:
        """Get booking with all related objects."""
        async with async_session() as session:
            result = await session.execute(
                select(Booking)
                .options(
                    selectinload(Booking.user),
                    selectinload(Booking.banya).selectinload(Banya.owner),
                    selectinload(Booking.bath_master).selectinload(BathMaster.user),
                )
                .where(Booking.id == booking_id)
            )
            return result.scalar_one_or_none()

    def _format_booking_info(self, booking: Booking) -> str:
        """Format booking info for notification."""
        date_str = booking.date.strftime("%d.%m.%Y")

        booking_type_names = {
            BookingType.BANYA_ONLY: "Баня",
            BookingType.BANYA_WITH_MASTER: "Баня + мастер",
            BookingType.MASTER_AT_BANYA: "Мастер в бане",
            BookingType.MASTER_HOME_VISIT: "Выезд мастера",
        }
        type_name = booking_type_names.get(booking.booking_type, "Бронирование")

        lines = [
            f"<b>{type_name}</b>",
            f"📅 Дата: {date_str}",
            f"🕐 Время: {booking.start_time}",
            f"⏱ Длительность: {booking.duration_hours} ч.",
        ]

        if booking.banya:
            lines.append(f"🏠 Баня: {booking.banya.name}")

        if booking.bath_master:
            master_name = booking.bath_master.user.first_name if booking.bath_master.user else "Мастер"
            lines.append(f"👨‍🍳 Мастер: {master_name}")

        if booking.client_address:
            lines.append(f"📍 Адрес: {booking.client_address}")

        lines.append(f"💰 Сумма: {booking.total_price} ₽")

        return "\n".join(lines)

    def _get_status_text(self, booking: Booking) -> str:
        """Get human-readable status text."""
        if booking.status == BookingStatus.PENDING:
            return "⏳ Ожидает подтверждения клиента"
        elif booking.status == BookingStatus.AWAITING_CONFIRMATIONS:
            confirmations = []
            if booking.banya and not booking.banya_confirmed:
                confirmations.append("бани")
            if booking.bath_master and not booking.master_confirmed:
                confirmations.append("мастера")
            if confirmations:
                return f"⏳ Ожидает подтверждения: {', '.join(confirmations)}"
            return "⏳ Ожидает подтверждений"
        elif booking.status == BookingStatus.CONFIRMED:
            return "✅ Подтверждено"
        elif booking.status == BookingStatus.CANCELLED:
            return "❌ Отменено"
        elif booking.status == BookingStatus.COMPLETED:
            return "✔️ Завершено"
        return str(booking.status.value)

    # ==================== CLIENT NOTIFICATIONS ====================

    async def notify_client_booking_created(self, booking: Booking):
        """Notify client that booking was created."""
        if not booking.user:
            return

        text = (
            "📝 <b>Бронирование создано!</b>\n\n"
            f"{self._format_booking_info(booking)}\n\n"
            "Подтвердите бронирование, чтобы отправить запрос."
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=f"client_confirm_booking_{booking.id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data=f"client_cancel_booking_{booking.id}"
                ),
            ]
        ])

        try:
            await self.bot.send_message(
                chat_id=booking.user.telegram_id,
                text=text,
                reply_markup=keyboard
            )
        except Exception:
            pass

    async def notify_client_status_changed(self, booking: Booking):
        """Notify client about booking status change."""
        if not booking.user:
            return

        status_text = self._get_status_text(booking)

        text = (
            "🔔 <b>Статус бронирования обновлён</b>\n\n"
            f"{self._format_booking_info(booking)}\n\n"
            f"<b>Статус:</b> {status_text}"
        )

        keyboard = None
        if booking.status in [BookingStatus.PENDING, BookingStatus.AWAITING_CONFIRMATIONS]:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="❌ Отменить бронирование",
                    callback_data=f"client_cancel_booking_{booking.id}"
                )]
            ])

        try:
            await self.bot.send_message(
                chat_id=booking.user.telegram_id,
                text=text,
                reply_markup=keyboard
            )
        except Exception:
            pass

    async def notify_client_booking_confirmed(self, booking: Booking):
        """Notify client that booking is fully confirmed."""
        if not booking.user:
            return

        text = (
            "🎉 <b>Бронирование подтверждено!</b>\n\n"
            f"{self._format_booking_info(booking)}\n\n"
            "Все участники подтвердили бронирование. Ждём вас!"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="❌ Отменить бронирование",
                callback_data=f"client_cancel_booking_{booking.id}"
            )]
        ])

        try:
            await self.bot.send_message(
                chat_id=booking.user.telegram_id,
                text=text,
                reply_markup=keyboard
            )
        except Exception:
            pass

    async def notify_client_booking_cancelled(
        self, booking: Booking, cancelled_by: CancelledBy, reason: Optional[str] = None
    ):
        """Notify client that booking was cancelled."""
        if not booking.user:
            return

        cancelled_by_text = {
            CancelledBy.CLIENT: "вами",
            CancelledBy.BANYA: "баней",
            CancelledBy.BATH_MASTER: "мастером",
            CancelledBy.ADMIN: "администратором",
        }

        text = (
            "❌ <b>Бронирование отменено</b>\n\n"
            f"{self._format_booking_info(booking)}\n\n"
            f"Отменено: {cancelled_by_text.get(cancelled_by, 'неизвестно')}"
        )

        if reason:
            text += f"\nПричина: {reason}"

        try:
            await self.bot.send_message(
                chat_id=booking.user.telegram_id,
                text=text
            )
        except Exception:
            pass

    # ==================== BANYA OWNER NOTIFICATIONS ====================

    async def notify_banya_new_booking(self, booking: Booking):
        """Notify banya owner about new booking request."""
        if not booking.banya or not booking.banya.owner:
            return

        client_name = booking.user.first_name if booking.user else "Клиент"

        text = (
            "🔔 <b>Новый запрос на бронирование!</b>\n\n"
            f"👤 Клиент: {client_name}\n"
            f"{self._format_booking_info(booking)}\n\n"
            "Подтвердите или отклоните бронирование."
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=f"banya_confirm_{booking.id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"banya_reject_{booking.id}"
                ),
            ]
        ])

        try:
            await self.bot.send_message(
                chat_id=booking.banya.owner.telegram_id,
                text=text,
                reply_markup=keyboard
            )
        except Exception:
            pass

    async def notify_banya_booking_cancelled(
        self, booking: Booking, cancelled_by: CancelledBy, reason: Optional[str] = None
    ):
        """Notify banya owner that booking was cancelled."""
        if not booking.banya or not booking.banya.owner:
            return

        cancelled_by_text = {
            CancelledBy.CLIENT: "клиентом",
            CancelledBy.BANYA: "вами",
            CancelledBy.BATH_MASTER: "мастером",
            CancelledBy.ADMIN: "администратором",
        }

        client_name = booking.user.first_name if booking.user else "Клиент"

        text = (
            "❌ <b>Бронирование отменено</b>\n\n"
            f"👤 Клиент: {client_name}\n"
            f"{self._format_booking_info(booking)}\n\n"
            f"Отменено: {cancelled_by_text.get(cancelled_by, 'неизвестно')}"
        )

        if reason:
            text += f"\nПричина: {reason}"

        try:
            await self.bot.send_message(
                chat_id=booking.banya.owner.telegram_id,
                text=text
            )
        except Exception:
            pass

    # ==================== BATH MASTER NOTIFICATIONS ====================

    async def notify_master_new_booking(self, booking: Booking):
        """Notify bath master about new booking request."""
        if not booking.bath_master or not booking.bath_master.user:
            return

        client_name = booking.user.first_name if booking.user else "Клиент"

        text = (
            "🔔 <b>Новый запрос на бронирование!</b>\n\n"
            f"👤 Клиент: {client_name}\n"
            f"{self._format_booking_info(booking)}\n\n"
            "Подтвердите или отклоните бронирование."
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=f"master_confirm_{booking.id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"master_reject_{booking.id}"
                ),
            ]
        ])

        try:
            await self.bot.send_message(
                chat_id=booking.bath_master.user.telegram_id,
                text=text,
                reply_markup=keyboard
            )
        except Exception:
            pass

    async def notify_master_booking_cancelled(
        self, booking: Booking, cancelled_by: CancelledBy, reason: Optional[str] = None
    ):
        """Notify bath master that booking was cancelled."""
        if not booking.bath_master or not booking.bath_master.user:
            return

        cancelled_by_text = {
            CancelledBy.CLIENT: "клиентом",
            CancelledBy.BANYA: "баней",
            CancelledBy.BATH_MASTER: "вами",
            CancelledBy.ADMIN: "администратором",
        }

        client_name = booking.user.first_name if booking.user else "Клиент"

        text = (
            "❌ <b>Бронирование отменено</b>\n\n"
            f"👤 Клиент: {client_name}\n"
            f"{self._format_booking_info(booking)}\n\n"
            f"Отменено: {cancelled_by_text.get(cancelled_by, 'неизвестно')}"
        )

        if reason:
            text += f"\nПричина: {reason}"

        try:
            await self.bot.send_message(
                chat_id=booking.bath_master.user.telegram_id,
                text=text
            )
        except Exception:
            pass

    # ==================== BULK NOTIFICATIONS ====================

    async def notify_all_booking_cancelled(
        self,
        booking: Booking,
        cancelled_by: CancelledBy,
        reason: Optional[str] = None,
        exclude_telegram_id: Optional[int] = None
    ):
        """Notify all participants about booking cancellation."""
        # Notify client (if not the one who cancelled)
        if booking.user and booking.user.telegram_id != exclude_telegram_id:
            await self.notify_client_booking_cancelled(booking, cancelled_by, reason)

        # Notify banya owner (if not the one who cancelled)
        if (booking.banya and booking.banya.owner and
            booking.banya.owner.telegram_id != exclude_telegram_id):
            await self.notify_banya_booking_cancelled(booking, cancelled_by, reason)

        # Notify bath master (if not the one who cancelled)
        if (booking.bath_master and booking.bath_master.user and
            booking.bath_master.user.telegram_id != exclude_telegram_id):
            await self.notify_master_booking_cancelled(booking, cancelled_by, reason)

    async def notify_awaiting_confirmations(self, booking: Booking):
        """Notify banya and/or master that client confirmed and they need to confirm too."""
        # Notify banya owner
        if booking.banya and not booking.banya_confirmed:
            await self.notify_banya_new_booking(booking)

        # Notify bath master
        if booking.bath_master and booking.master_confirmed is None:
            await self.notify_master_new_booking(booking)
