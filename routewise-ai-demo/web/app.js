const agents = ['central_agent', 'flight_desk_agent', 'day_plan_agent', 'edit_agent'];

let sessionId = null;
let tripState = null;
let isLoading = false;
let thinkingTimer = null;
let thinkingStep = 0;

const thinkingStages = [
	{
		agent_id: 'central_agent',
		message: 'Reading the request and normalizing trip intent.',
	},
	{
		agent_id: 'flight_desk_agent',
		message: 'Checking whether flight tools have enough route and date information.',
	},
	{
		agent_id: 'day_plan_agent',
		message: 'Preparing itinerary constraints for the day plan.',
	},
];

const elements = {
	chatLog: document.getElementById('chat-log'),
	emptyChat: document.getElementById('empty-chat'),
	assistantTurn: document.getElementById('assistant-turn'),
	resultTurn: document.getElementById('result-turn'),
	health: document.getElementById('health-pill'),
	tripForm: document.getElementById('trip-form'),
	tripPrompt: document.getElementById('trip-prompt'),
	runButton: document.getElementById('run-button'),
	editForm: document.getElementById('edit-form'),
	editPrompt: document.getElementById('edit-prompt'),
	editButton: document.getElementById('edit-button'),
	assistantMessage: document.getElementById('assistant-message'),
	errorBox: document.getElementById('error-box'),
	missingBox: document.getElementById('missing-box'),
	title: document.getElementById('trip-title'),
	summary: document.getElementById('trip-summary'),
	origin: document.getElementById('origin-code'),
	destination: document.getElementById('destination-code'),
	routeChip: document.querySelector('.route-chip'),
	metrics: document.getElementById('metrics'),
	flightMessage: document.getElementById('flight-message'),
	flightCards: document.getElementById('flight-cards'),
	hotelPanel: document.getElementById('hotel-panel'),
	hotelSuggestions: document.getElementById('hotel-suggestions'),
	placesPanel: document.getElementById('places-panel'),
	placeShortlist: document.getElementById('place-shortlist'),
	itinerary: document.getElementById('itinerary'),
	budgetPanel: document.getElementById('budget-panel'),
	budgetNotes: document.getElementById('budget-notes'),
	timeline: document.getElementById('timeline'),
	flightMeta: document.getElementById('flight-meta'),
	flightCalendar: document.getElementById('flight-calendar'),
};

function money(value, currency = 'USD') {
	if (value === null || value === undefined || value === '') return '';
	const amount = Number(value);
	return Number.isFinite(amount) && amount > 0 ? `${currency} ${amount.toFixed(0)}` : '';
}

function duration(minutes) {
	const value = Number(minutes);
	if (!Number.isFinite(value) || value <= 0) return '';
	const hours = Math.floor(value / 60);
	const mins = value % 60;
	return mins ? `${hours}h ${mins}m` : `${hours}h`;
}

function flightKey(flight = {}) {
	return [
		flight.id,
		flight.origin,
		flight.destination,
		flight.departure_date,
		flight.arrival_date,
		flight.airline,
		flight.price,
		flight.duration_minutes,
		flight.stops,
	]
		.map((value) => String(value ?? ''))
		.join('|');
}

function renderFlightCard(flight = {}, { recommended = false } = {}) {
	const meta = [flight.airline, `${flight.stops || 0} stops`, duration(flight.duration_minutes)]
		.filter(Boolean)
		.join(' · ');
	const dates = [flight.departure_date, flight.arrival_date].filter(Boolean).join(' -> ');
	const route = [flight.origin, flight.destination].filter(Boolean).join(' -> ') || 'Flight option';
	return `
		<article class="flight-card ${recommended ? 'recommended-flight' : ''}">
			${recommended ? '<div class="recommended-label">Recommended flight</div>' : ''}
			<header><b>${escapeHtml(route)}</b><b>${escapeHtml(money(flight.price, flight.currency))}</b></header>
			${meta ? `<p class="muted">${escapeHtml(meta)}</p>` : ''}
			${dates ? `<p class="muted">${escapeHtml(dates)}</p>` : ''}
		</article>
	`;
}

function label(value) {
	return String(value || '')
		.replaceAll('_', ' ')
		.replace(/\b\w/g, (char) => char.toUpperCase());
}

function escapeHtml(value) {
	return String(value ?? '')
		.replaceAll('&', '&amp;')
		.replaceAll('<', '&lt;')
		.replaceAll('>', '&gt;')
		.replaceAll('"', '&quot;')
		.replaceAll("'", '&#039;');
}

function appendUserMessage(message) {
	if (!elements.chatLog) return;
	elements.emptyChat?.classList.add('hidden');
	const wrapper = document.createElement('article');
	wrapper.className = 'message user';
	wrapper.innerHTML = `
		<div class="message-body">
			<p class="message-kicker">You</p>
			<div class="bubble">${escapeHtml(message)}</div>
		</div>
		<div class="avatar">U</div>
	`;
	if (elements.assistantTurn?.parentNode === elements.chatLog) {
		elements.chatLog.insertBefore(wrapper, elements.assistantTurn);
	} else {
		elements.chatLog.appendChild(wrapper);
	}
	wrapper.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

function showAssistantTurn() {
	elements.emptyChat?.classList.add('hidden');
	elements.assistantTurn?.classList.remove('hidden');
}

function loadingStatusHtml(labelText = 'Thinking') {
	return `
		<span class="loading-status" aria-label="${escapeHtml(labelText)}">
			<span class="loading-dot"></span>
			<span>${escapeHtml(labelText)}</span>
		</span>
	`;
}

function renderThinkingBubble(stage) {
	elements.assistantMessage.innerHTML = `
		<div class="thinking-line">
			${loadingStatusHtml('Thinking')}
			<span>${escapeHtml(stage.message)}</span>
		</div>
	`;
}

function liveThinkingTrace() {
	const currentIndex = thinkingStep % thinkingStages.length;
	return thinkingStages.slice(0, currentIndex + 1).map((stage, index) => ({
		agent_id: stage.agent_id,
		status: index === currentIndex ? 'thinking' : 'queued',
		message: index === currentIndex ? stage.message : 'Waiting for its handoff.',
		live: index === currentIndex,
	}));
}

function startThinkingIndicator() {
	stopThinkingIndicator();
	thinkingStep = 0;
	const render = () => {
		const trace = liveThinkingTrace();
		const activeStage = trace[trace.length - 1];
		renderThinkingBubble(activeStage);
		updateAgentRail(trace);
		renderTimeline(trace, { live: true });
	};
	render();
	thinkingTimer = window.setInterval(() => {
		thinkingStep += 1;
		render();
	}, 1800);
}

function stopThinkingIndicator({ clearBubble = false } = {}) {
	if (thinkingTimer) window.clearInterval(thinkingTimer);
	thinkingTimer = null;
	if (clearBubble && elements.assistantMessage?.querySelector('.loading-status')) {
		elements.assistantMessage.textContent = '';
	}
}

function setLoading(nextValue) {
	isLoading = nextValue;
	elements.runButton.disabled = isLoading || !elements.tripPrompt.value.trim();
	elements.editButton.disabled = isLoading || !elements.editPrompt.value.trim() || !tripState?.itinerary?.length;
}

function updateAgentRail(trace = []) {
	const statuses = Object.fromEntries(agents.map((agent) => [agent, 'idle']));
	trace.forEach((event) => {
		if (event.agent_id && event.status) statuses[event.agent_id] = event.status;
	});
	agents.forEach((agent) => {
		const card = document.querySelector(`[data-agent="${agent}"]`);
		const status = statuses[agent] || 'idle';
		card.classList.remove('thinking', 'done', 'skipped', 'error', 'queued', 'idle');
		card.classList.add(status);
		const labelText = status === 'idle' ? 'Idle' : status;
		card.querySelector('em').innerHTML = status === 'thinking' ? loadingStatusHtml('Thinking') : escapeHtml(labelText);
	});
}

function renderTimeline(trace = [], { live = false } = {}) {
	const visibleTrace = live ? trace : trace.filter((event) => event.status !== 'thinking' && event.status !== 'queued');
	if (!visibleTrace.length) {
		elements.timeline.innerHTML = '<div class="empty-state">Waiting for agent activity.</div>';
		return;
	}
	elements.timeline.innerHTML = visibleTrace
		.map((event) => {
			const agentLabel = label(event.agent_id);
			const statusLabel = event.status === 'thinking' && (event.live || live) ? loadingStatusHtml('Thinking') : escapeHtml(event.status);
			const isLiveThinking = live && event.status === 'thinking';
			return `
				<div class="timeline-item ${isLiveThinking ? 'thinking' : ''}">
					<strong>${escapeHtml(agentLabel)}<span>${statusLabel}</span></strong>
					<p>${escapeHtml(event.message || '')}</p>
				</div>
			`;
		})
		.join('');
}

function renderMetrics(state) {
	const flightPreferences =
		state.flight_preferences && typeof state.flight_preferences === 'object' ? state.flight_preferences : {};
	const dateWindow = [flightPreferences.date_window_start, flightPreferences.date_window_end].filter(Boolean).join(' -> ');
	const rows = [
		['Origin', state.origin],
		['Destination', state.destination],
		['Dates', [state.start_date, state.end_date].filter(Boolean).join(' -> ')],
		['Window', !state.start_date ? dateWindow : ''],
		['Length', state.duration_days ? `${state.duration_days} days` : ''],
		['Travelers', state.travelers],
		['Budget', state.budget ? money(state.budget, state.budget_currency) : ''],
	].filter(([, value]) => value);
	elements.metrics.innerHTML = rows
		.map(([label, value]) => `<div class="metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`)
		.join('');
}

function renderFlights(flightSearch = {}) {
	const options = Array.isArray(flightSearch.options) ? flightSearch.options : [];
	const calendar = Array.isArray(flightSearch.calendar) ? flightSearch.calendar : [];
	const selectedOption =
		flightSearch.selected_option && typeof flightSearch.selected_option === 'object'
			? flightSearch.selected_option
			: null;
	elements.flightMessage.textContent = flightSearch.message || 'No live flight cards yet.';
	elements.flightMeta.innerHTML = [
		flightSearch.strategy ? `<span>${escapeHtml(label(flightSearch.strategy))}</span>` : '',
		flightSearch.reasoning ? `<p>${escapeHtml(flightSearch.reasoning)}</p>` : '',
	].join('');
	if (calendar.length) {
		const selected = flightSearch.selected_calendar_pick || {};
		elements.flightCalendar.innerHTML = `
			<div class="section-label">Calendar candidates</div>
			${calendar
				.slice(0, 4)
				.map((row) => {
					const active =
						row.departure_date === selected.departure_date &&
						(row.return_date || '') === (selected.return_date || '');
					const routeDates = [row.departure_date, row.return_date].filter(Boolean).join(' -> ');
					return `
						<div class="calendar-row ${active ? 'selected' : ''}">
							<span>${escapeHtml(routeDates || 'Candidate date')}</span>
							<strong>${escapeHtml(money(row.price, row.currency))}</strong>
						</div>
					`;
				})
				.join('')}
		`;
	} else {
		elements.flightCalendar.innerHTML = '';
	}
	if (!options.length && !selectedOption) {
		elements.flightCards.innerHTML = '';
		return;
	}
	const selectedKey = selectedOption ? flightKey(selectedOption) : '';
	const alternateOptions = options.filter((flight) => flightKey(flight) !== selectedKey).slice(0, 3);
	elements.flightCards.innerHTML = [
		selectedOption ? renderFlightCard(selectedOption, { recommended: true }) : '',
		alternateOptions.length ? '<div class="flight-section-title">Other options</div>' : '',
		...alternateOptions.map((flight) => renderFlightCard(flight)),
	].join('');
}

function renderHotels(hotels = []) {
	const rows = Array.isArray(hotels) ? hotels : [];
	elements.hotelPanel?.classList.toggle('hidden', !rows.length);
	if (!rows.length) {
		if (elements.hotelSuggestions) elements.hotelSuggestions.innerHTML = '';
		return;
	}
	elements.hotelSuggestions.innerHTML = rows
		.slice(0, 5)
		.map((hotel) => {
			const meta = [hotel.area, hotel.type, hotel.budget_level].filter(Boolean).join(' · ');
			return `
				<article class="hotel-card">
					<header><b>${escapeHtml(hotel.name || 'Hotel option')}</b></header>
					${meta ? `<p class="muted">${escapeHtml(meta)}</p>` : ''}
					${hotel.why ? `<p>${escapeHtml(hotel.why)}</p>` : ''}
				</article>
			`;
		})
		.join('');
}

function renderPlaceShortlist(places = []) {
	const rows = Array.isArray(places) ? places : [];
	elements.placesPanel?.classList.toggle('hidden', !rows.length);
	if (!rows.length) {
		if (elements.placeShortlist) elements.placeShortlist.innerHTML = '';
		return;
	}
	elements.placeShortlist.innerHTML = rows
		.slice(0, 12)
		.map((place) => {
			const meta = [place.area, place.type].filter(Boolean).join(' · ');
			return `
				<article class="place-pill">
					<strong>${escapeHtml(place.name || 'Place')}</strong>
					${meta ? `<span>${escapeHtml(meta)}</span>` : ''}
					${place.why ? `<p>${escapeHtml(place.why)}</p>` : ''}
				</article>
			`;
		})
		.join('');
}

function renderItinerary(days = []) {
	if (!days.length) {
		elements.itinerary.innerHTML = '<div class="empty-state">The itinerary will appear after the first request.</div>';
		return;
	}
	elements.itinerary.innerHTML = days
		.map((day, index) => `
			<article class="day-card">
				<header><b>Day ${escapeHtml(day.day || index + 1)}</b><b>${escapeHtml(day.theme || 'Open day')}</b></header>
				<div class="day-blocks">
					<p><strong>Morning</strong>${escapeHtml(day.morning || 'Open planning block')}</p>
					<p><strong>Afternoon</strong>${escapeHtml(day.afternoon || 'Open planning block')}</p>
					<p><strong>Evening</strong>${escapeHtml(day.evening || 'Open planning block')}</p>
				</div>
				<p class="muted">${escapeHtml([day.pace || 'balanced pace', day.estimated_cost].filter(Boolean).join(' · '))}</p>
			</article>
		`)
		.join('');
}

function renderTrip(state = {}, missingFields = []) {
	const hasCompleteResult = !missingFields.length && (state.itinerary?.length || state.flight_search?.options?.length);
	if (!hasCompleteResult) {
		elements.resultTurn?.classList.add('hidden');
		elements.editForm?.classList.add('hidden');
		elements.editPrompt.disabled = true;
		elements.editButton.disabled = true;
		return;
	}
	elements.resultTurn?.classList.remove('hidden');
	elements.title.textContent = state.title || 'RouteWise trip plan';
	elements.summary.textContent =
		state.summary || 'Start with one natural-language request. The agents will turn it into a base trip plan.';
	const hasRoute = Boolean(state.origin && state.destination);
	elements.routeChip?.classList.toggle('hidden', !hasRoute);
	elements.origin.textContent = state.origin || '';
	elements.destination.textContent = state.destination || 'DEST';
	renderMetrics(state);
	renderHotels(state.hotel_suggestions || []);
	renderPlaceShortlist(state.place_shortlist || []);
	renderFlights(state.flight_search || {});
	renderItinerary(state.itinerary || []);

	if (state.budget_notes) {
		elements.budgetPanel.classList.remove('hidden');
		elements.budgetNotes.textContent = state.budget_notes;
	} else {
		elements.budgetPanel.classList.add('hidden');
	}

	elements.missingBox.classList.add('hidden');

	const canEdit = Boolean(state.itinerary?.length);
	elements.editForm?.classList.toggle('hidden', !canEdit);
	elements.editPrompt.disabled = !canEdit;
	elements.editButton.disabled = !canEdit || !elements.editPrompt.value.trim() || isLoading;
}

async function sendMessage(message) {
	const submittedMessage = message.trim();
	if (!submittedMessage || isLoading) return;
	setLoading(true);
	elements.errorBox.classList.add('hidden');
	appendUserMessage(submittedMessage);
	showAssistantTurn();
	startThinkingIndicator();
	try {
		const response = await fetch('/api/message', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				session_id: sessionId,
				message: submittedMessage,
				trip_state: tripState,
			}),
		});
		const data = await response.json();
		if (!response.ok || data.ok === false) throw new Error(data.error || 'RouteWise request failed');
		sessionId = data.session_id || sessionId;
		tripState = data.trip_state || tripState;
		stopThinkingIndicator();
		elements.assistantMessage.textContent = data.assistant_message || 'RouteWise AI updated the plan.';
		updateAgentRail(data.agent_trace || []);
		renderTimeline(data.agent_trace || []);
		renderTrip(tripState || {}, data.missing_fields || []);
		elements.tripPrompt.value = '';
		elements.editPrompt.value = '';
	} catch (error) {
		elements.errorBox.textContent = error.message || 'RouteWise request failed';
		elements.errorBox.classList.remove('hidden');
		stopThinkingIndicator({ clearBubble: true });
		updateAgentRail([]);
		renderTimeline([
			{
				agent_id: 'central_agent',
				status: 'error',
				message: error.message || 'RouteWise request failed',
			},
		]);
		elements.assistantMessage.textContent = 'The demo backend returned an error.';
	} finally {
		stopThinkingIndicator();
		setLoading(false);
	}
}

async function loadHealth() {
	try {
		const response = await fetch('/api/health');
		const data = await response.json();
		if (!data.groq_configured) elements.health.textContent = 'GROQ_API_KEY missing';
		else if (!data.rapidapi_configured) elements.health.textContent = 'Groq configured · RapidAPI optional';
		else elements.health.textContent = 'Groq + RapidAPI configured';
	} catch (error) {
		elements.health.textContent = 'Backend not reachable';
	}
}

elements.tripPrompt.addEventListener('input', () => setLoading(false));
elements.editPrompt.addEventListener('input', () => setLoading(false));
elements.tripForm.addEventListener('submit', (event) => {
	event.preventDefault();
	sendMessage(elements.tripPrompt.value);
});
elements.editForm.addEventListener('submit', (event) => {
	event.preventDefault();
	sendMessage(elements.editPrompt.value);
});

loadHealth();
