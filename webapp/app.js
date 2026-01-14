// Initialize Telegram WebApp
const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

// API Base URL (will be set from environment or config)
const API_BASE = window.location.origin + '/api';

// State
let currentUser = null;
let selectedBanya = null;
let selectedDate = null;
let selectedTime = null;
let selectedDuration = 2;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    loadCities();
    initFilters();

    // Get user from Telegram
    if (tg.initDataUnsafe?.user) {
        initUser(tg.initDataUnsafe.user);
    }
});

// Tab Navigation
function initTabs() {
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const tabId = tab.dataset.tab;
            switchTab(tabId);
        });
    });
}

function switchTab(tabId) {
    // Update nav tabs
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`[data-tab="${tabId}"]`).classList.add('active');

    // Update content
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.getElementById(`${tabId}-tab`).classList.add('active');

    // Load data for tab
    if (tabId === 'bookings') {
        loadBookings();
    } else if (tabId === 'profile') {
        loadProfile();
    }
}

// User initialization
async function initUser(telegramUser) {
    try {
        const response = await fetch(`${API_BASE}/users`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                telegram_id: telegramUser.id,
                username: telegramUser.username,
                first_name: telegramUser.first_name,
                last_name: telegramUser.last_name
            })
        });
        currentUser = await response.json();
    } catch (error) {
        console.error('Error initializing user:', error);
    }
}

// Load cities
async function loadCities() {
    try {
        const response = await fetch(`${API_BASE}/banyas/cities`);
        const cities = await response.json();

        const select = document.getElementById('city-select');
        cities.forEach(city => {
            const option = document.createElement('option');
            option.value = city.id;
            option.textContent = city.name;
            select.appendChild(option);
        });

        select.addEventListener('change', () => loadBanyas());
    } catch (error) {
        console.error('Error loading cities:', error);
    }
}

// Init filters
function initFilters() {
    document.querySelectorAll('.filter-chip input').forEach(input => {
        input.addEventListener('change', () => loadBanyas());
    });
}

// Load banyas
async function loadBanyas() {
    const cityId = document.getElementById('city-select').value;
    const container = document.getElementById('banyas-list');

    if (!cityId) {
        container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">🏙</div><p>Выберите город для поиска</p></div>';
        return;
    }

    container.innerHTML = '<div class="loading">Загрузка...</div>';

    // Build query params
    const params = new URLSearchParams({ city_id: cityId });

    if (document.getElementById('filter-russian').checked) {
        params.append('has_russian_banya', 'true');
    }
    if (document.getElementById('filter-finnish').checked) {
        params.append('has_finnish_sauna', 'true');
    }
    if (document.getElementById('filter-hammam').checked) {
        params.append('has_hammam', 'true');
    }
    if (document.getElementById('filter-pool').checked) {
        params.append('has_pool', 'true');
    }

    try {
        const response = await fetch(`${API_BASE}/banyas?${params}`);
        const banyas = await response.json();

        if (banyas.length === 0) {
            container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">😔</div><p>Бани не найдены</p></div>';
            return;
        }

        container.innerHTML = banyas.map(banya => `
            <div class="banya-card" onclick="openBanyaDetail(${banya.id})">
                <div class="banya-card-header">
                    <span class="banya-name">${banya.name}</span>
                    <span class="banya-rating">⭐ ${banya.rating.toFixed(1)}</span>
                </div>
                <div class="banya-address">📍 ${banya.address}</div>
                <div class="banya-tags">
                    ${banya.has_russian_banya ? '<span class="banya-tag">🇷🇺 Русская</span>' : ''}
                    ${banya.has_finnish_sauna ? '<span class="banya-tag">🇫🇮 Финская</span>' : ''}
                    ${banya.has_hammam ? '<span class="banya-tag">🇹🇷 Хаммам</span>' : ''}
                </div>
                <div class="banya-price">от ${banya.price_per_hour} ₽/час</div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Error loading banyas:', error);
        container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">❌</div><p>Ошибка загрузки</p></div>';
    }
}

// Open banya detail
async function openBanyaDetail(banyaId) {
    try {
        const response = await fetch(`${API_BASE}/banyas/${banyaId}`);
        const banya = await response.json();
        selectedBanya = banya;

        const features = [];
        if (banya.has_russian_banya) features.push('🇷🇺 Русская баня');
        if (banya.has_finnish_sauna) features.push('🇫🇮 Финская сауна');
        if (banya.has_hammam) features.push('🇹🇷 Хаммам');
        if (banya.has_pool) features.push('🏊 Бассейн');
        if (banya.has_jacuzzi) features.push('🛁 Джакузи');
        if (banya.has_cold_plunge) features.push('❄️ Купель');
        if (banya.has_rest_room) features.push('🛋 Комната отдыха');
        if (banya.has_billiards) features.push('🎱 Бильярд');
        if (banya.has_karaoke) features.push('🎤 Караоке');
        if (banya.has_bbq) features.push('🍖 Мангал');
        if (banya.has_parking) features.push('🅿️ Парковка');

        const services = [];
        if (banya.provides_veniks) services.push('🌿 Веники');
        if (banya.provides_towels) services.push('🧺 Полотенца');
        if (banya.provides_robes) services.push('🥋 Халаты');
        if (banya.provides_food) services.push('🍽 Еда');
        if (banya.provides_drinks) services.push('🍺 Напитки');

        document.getElementById('banya-detail').innerHTML = `
            <div class="banya-detail">
                <h2 class="banya-detail-name">${banya.name}</h2>
                <div class="banya-detail-rating">⭐ ${banya.rating.toFixed(1)} (${banya.rating_count} отзывов)</div>

                <div class="banya-detail-section">
                    <h3>📍 Адрес</h3>
                    <p>${banya.address}</p>
                </div>

                <div class="banya-detail-section">
                    <h3>🕐 Время работы</h3>
                    <p>${banya.opening_time} - ${banya.closing_time}</p>
                </div>

                <div class="banya-detail-section">
                    <h3>👥 Вместимость</h3>
                    <p>До ${banya.max_guests} гостей</p>
                </div>

                <div class="banya-detail-section">
                    <h3>💰 Цена</h3>
                    <p>${banya.price_per_hour} ₽/час (мин. ${banya.min_hours} ч.)</p>
                </div>

                ${features.length > 0 ? `
                <div class="banya-detail-section">
                    <h3>✨ Удобства</h3>
                    <div class="banya-features">
                        ${features.map(f => `<span class="banya-feature">${f}</span>`).join('')}
                    </div>
                </div>
                ` : ''}

                ${services.length > 0 ? `
                <div class="banya-detail-section">
                    <h3>🎁 Услуги</h3>
                    <div class="banya-features">
                        ${services.map(s => `<span class="banya-feature">${s}</span>`).join('')}
                    </div>
                </div>
                ` : ''}

                ${banya.description ? `
                <div class="banya-detail-section">
                    <h3>📝 Описание</h3>
                    <p>${banya.description}</p>
                </div>
                ` : ''}

                <button class="btn btn-primary" onclick="openBookingForm(${banya.id})">
                    📅 Забронировать
                </button>
            </div>
        `;

        document.getElementById('banya-modal').classList.remove('hidden');
    } catch (error) {
        console.error('Error loading banya:', error);
        tg.showAlert('Ошибка загрузки');
    }
}

function closeModal() {
    document.getElementById('banya-modal').classList.add('hidden');
}

// Booking form
async function openBookingForm(banyaId) {
    closeModal();
    selectedDate = null;
    selectedTime = null;
    selectedDuration = selectedBanya.min_hours;

    // Generate next 7 days
    const dates = [];
    const today = new Date();
    for (let i = 0; i < 7; i++) {
        const date = new Date(today);
        date.setDate(date.getDate() + i);
        const dayNames = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];
        dates.push({
            value: date.toISOString().split('T')[0],
            label: `${dayNames[date.getDay()]}, ${date.getDate()}.${(date.getMonth() + 1).toString().padStart(2, '0')}`
        });
    }

    document.getElementById('booking-form').innerHTML = `
        <div class="booking-form">
            <h2>📅 Бронирование</h2>
            <p style="color: var(--tg-theme-hint-color); margin-bottom: 20px;">${selectedBanya.name}</p>

            <div class="form-group">
                <label class="form-label">Дата</label>
                <select class="form-input" id="booking-date" onchange="loadTimeSlots()">
                    <option value="">Выберите дату</option>
                    ${dates.map(d => `<option value="${d.value}">${d.label}</option>`).join('')}
                </select>
            </div>

            <div class="form-group">
                <label class="form-label">Время</label>
                <div id="time-slots-container" class="time-slots">
                    <p style="color: var(--tg-theme-hint-color); grid-column: 1/-1; text-align: center;">Сначала выберите дату</p>
                </div>
            </div>

            <div class="form-group">
                <label class="form-label">Продолжительность</label>
                <select class="form-input" id="booking-duration" onchange="updateBookingSummary()">
                    ${[selectedBanya.min_hours, selectedBanya.min_hours + 1, selectedBanya.min_hours + 2, selectedBanya.min_hours + 3].map(h =>
                        `<option value="${h}">${h} часа</option>`
                    ).join('')}
                </select>
            </div>

            <div id="booking-summary" class="booking-summary" style="display: none;">
            </div>

            <button class="btn btn-primary" id="confirm-booking-btn" onclick="confirmBooking()" disabled>
                Подтвердить бронирование
            </button>
        </div>
    `;

    document.getElementById('booking-modal').classList.remove('hidden');
}

async function loadTimeSlots() {
    const date = document.getElementById('booking-date').value;
    const container = document.getElementById('time-slots-container');

    if (!date) {
        container.innerHTML = '<p style="color: var(--tg-theme-hint-color); grid-column: 1/-1; text-align: center;">Сначала выберите дату</p>';
        return;
    }

    selectedDate = date;
    container.innerHTML = '<p style="color: var(--tg-theme-hint-color); grid-column: 1/-1; text-align: center;">Загрузка...</p>';

    try {
        const response = await fetch(`${API_BASE}/banyas/${selectedBanya.id}/available-slots?date=${date}`);
        const data = await response.json();

        if (data.slots.length === 0) {
            container.innerHTML = '<p style="color: var(--tg-theme-hint-color); grid-column: 1/-1; text-align: center;">Нет доступных слотов</p>';
            return;
        }

        container.innerHTML = data.slots.map(slot => `
            <div class="time-slot" onclick="selectTimeSlot('${slot}', this)">${slot}</div>
        `).join('');
    } catch (error) {
        console.error('Error loading slots:', error);
        container.innerHTML = '<p style="color: var(--tg-theme-hint-color); grid-column: 1/-1; text-align: center;">Ошибка загрузки</p>';
    }
}

function selectTimeSlot(time, element) {
    document.querySelectorAll('.time-slot').forEach(el => el.classList.remove('selected'));
    element.classList.add('selected');
    selectedTime = time;
    updateBookingSummary();
}

function updateBookingSummary() {
    selectedDuration = parseInt(document.getElementById('booking-duration').value);
    const summary = document.getElementById('booking-summary');
    const btn = document.getElementById('confirm-booking-btn');

    if (selectedDate && selectedTime) {
        const totalPrice = selectedBanya.price_per_hour * selectedDuration;

        summary.innerHTML = `
            <div class="summary-row">
                <span>Дата</span>
                <span>${selectedDate}</span>
            </div>
            <div class="summary-row">
                <span>Время</span>
                <span>${selectedTime}</span>
            </div>
            <div class="summary-row">
                <span>Длительность</span>
                <span>${selectedDuration} ч.</span>
            </div>
            <div class="summary-row">
                <span>Цена за час</span>
                <span>${selectedBanya.price_per_hour} ₽</span>
            </div>
            <div class="summary-row summary-total">
                <span>Итого</span>
                <span>${totalPrice} ₽</span>
            </div>
        `;
        summary.style.display = 'block';
        btn.disabled = false;
    } else {
        summary.style.display = 'none';
        btn.disabled = true;
    }
}

async function confirmBooking() {
    if (!currentUser) {
        tg.showAlert('Ошибка авторизации');
        return;
    }

    const btn = document.getElementById('confirm-booking-btn');
    btn.disabled = true;
    btn.textContent = 'Создание...';

    try {
        const response = await fetch(`${API_BASE}/bookings?telegram_id=${currentUser.telegram_id}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                banya_id: selectedBanya.id,
                date: `${selectedDate}T${selectedTime}:00`,
                start_time: selectedTime,
                duration_hours: selectedDuration,
                guests_count: 1
            })
        });

        if (response.ok) {
            closeBookingModal();
            tg.showAlert('Бронирование создано!');
            switchTab('bookings');
        } else {
            throw new Error('Booking failed');
        }
    } catch (error) {
        console.error('Error creating booking:', error);
        tg.showAlert('Ошибка создания бронирования');
        btn.disabled = false;
        btn.textContent = 'Подтвердить бронирование';
    }
}

function closeBookingModal() {
    document.getElementById('booking-modal').classList.add('hidden');
}

// Load bookings
async function loadBookings() {
    const container = document.getElementById('bookings-list');

    if (!currentUser) {
        container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">👤</div><p>Войдите для просмотра бронирований</p></div>';
        return;
    }

    container.innerHTML = '<div class="loading">Загрузка...</div>';

    try {
        const response = await fetch(`${API_BASE}/bookings?telegram_id=${currentUser.telegram_id}`);
        const bookings = await response.json();

        if (bookings.length === 0) {
            container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📅</div><p>У вас пока нет бронирований</p></div>';
            return;
        }

        const statusLabels = {
            pending: 'Ожидает',
            confirmed: 'Подтверждено',
            cancelled: 'Отменено',
            completed: 'Завершено'
        };

        container.innerHTML = bookings.map(booking => `
            <div class="booking-card">
                <span class="booking-status ${booking.status}">${statusLabels[booking.status]}</span>
                <h3>#${booking.id}</h3>
                <div class="booking-info">
                    <div class="booking-info-row">
                        <span>Дата</span>
                        <span>${new Date(booking.date).toLocaleDateString('ru-RU')}</span>
                    </div>
                    <div class="booking-info-row">
                        <span>Время</span>
                        <span>${booking.start_time}</span>
                    </div>
                    <div class="booking-info-row">
                        <span>Длительность</span>
                        <span>${booking.duration_hours} ч.</span>
                    </div>
                    <div class="booking-info-row">
                        <span>Итого</span>
                        <span>${booking.total_price} ₽</span>
                    </div>
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Error loading bookings:', error);
        container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">❌</div><p>Ошибка загрузки</p></div>';
    }
}

// Load profile
async function loadProfile() {
    const container = document.getElementById('profile-content');

    if (!currentUser) {
        container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">👤</div><p>Данные профиля недоступны</p></div>';
        return;
    }

    const initials = (currentUser.first_name?.[0] || '') + (currentUser.last_name?.[0] || '');

    container.innerHTML = `
        <div class="profile-avatar">${initials || '👤'}</div>
        <h2 class="profile-name">${currentUser.first_name} ${currentUser.last_name || ''}</h2>
        <p class="profile-username">@${currentUser.username || 'не указан'}</p>

        ${currentUser.is_premium ? '<div class="profile-premium-badge">👑 Premium</div>' : ''}

        <div class="profile-stats">
            <div class="profile-stat">
                <div class="profile-stat-value">⭐ ${currentUser.rating.toFixed(1)}</div>
                <div class="profile-stat-label">Рейтинг</div>
            </div>
            <div class="profile-stat">
                <div class="profile-stat-value">${currentUser.rating_count}</div>
                <div class="profile-stat-label">Отзывов</div>
            </div>
        </div>

        ${!currentUser.is_premium ? `
        <button class="btn btn-secondary" onclick="showPremiumInfo()">
            👑 Подключить Premium
        </button>
        ` : ''}
    `;
}

function showPremiumInfo() {
    tg.showAlert('Premium подписка скоро будет доступна!');
}
