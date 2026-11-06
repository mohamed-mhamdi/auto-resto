const byId = id => document.getElementById(id);
const states = {free:'Libre',waiting:'En attente',acknowledged:'Pris en charge',served:'Servie',cleaning:'À nettoyer'};
const labels = {seat:'Clients installés',ack:'Pris en charge',serve:'Commande servie',leave:'Clients partis',ready:'Table prête',restore:'Occupation rétablie',alert:'Attente prolongée'};
const options = {
  free:[['seat','Installer']], waiting:[['ack','Prendre en charge'],['serve','Servi'],['leave','Départ']],
  acknowledged:[['serve','Servi'],['leave','Départ']], served:[['leave','Départ']], cleaning:[['ready','Table prête'],['restore','Toujours occupée']]
};
let snapshot;
let busy = false;
let updating = false;
let reportRequest = 0;
let visibleSignature;

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function notice(message) {
  byId('notice').hidden = !message;
  byId('notice').textContent = message || '';
}
async function request(url, options) {
  const response = await fetch(url, {signal: AbortSignal.timeout(4500), ...options});
  if (!response.ok) throw Error((await response.json()).error || 'Requête indisponible.');
  return response.json();
}
function duration(seconds) {
  const value = Math.max(0, Math.floor(seconds));
  return [Math.floor(value / 60), value % 60].map(n => String(n).padStart(2, '0')).join(':');
}
function metric(label, value) {
  const box = node('div', undefined, 'metric');
  box.append(node('p', label), node('strong', value));
  return box;
}
function line(label, detail, priority = false) {
  const row = node('div', undefined, priority ? 'line priority' : 'line');
  row.append(node('span', label), node('time', detail));
  return row;
}
async function action(table, value) {
  if (busy) return;
  busy = true;
  notice('');
  document.querySelectorAll('.actions button').forEach(button => button.disabled = true);
  try {
    await request('/api/action', {method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({table:table.id,revision:table.revision,action:value})});
  } catch (error) {
    notice(error.message);
  } finally {
    busy = false;
    await refresh();
    document.querySelectorAll('.actions button').forEach(button => button.disabled = false);
    const card = byId('table-' + table.id);
    (card?.querySelector('button') || byId('filter')).focus({preventScroll:true});
  }
}
function tableCard(table, now, demo) {
  const card = node('article', undefined, 'card');
  card.id = 'table-' + table.id;
  const head = node('div', undefined, 'card-head');
  head.append(node('h3', 'Table ' + String(table.id).padStart(2,'0')),
    node('span', states[table.state], 'badge ' + table.state));
  const time = table.state === 'free' ? 'Disponible' : duration(now - (table.state === 'cleaning' ? table.changed : table.seated));
  const observed = {empty:'vide', occupied:'occupée'}[table.observation] || 'à confirmer';
  const source = demo ? 'Démonstration' : table.online ? 'Vision · ' + observed : 'Caméra non connectée · mode manuel';
  card.append(head, node('div', time, 'timer'), node('p', source, 'camera'));
  const actions = node('div', undefined, 'actions');
  options[table.state].forEach(([value, label], index) => {
    const button = node('button', label, index === 0 ? 'primary' : '');
    button.dataset.action = value;
    button.setAttribute('aria-label', label + ' · Table ' + table.id);
    button.addEventListener('click', () => action(table, value));
    actions.append(button);
  });
  card.append(actions);
  return card;
}
function renderFloor() {
  if (!snapshot) return;
  const {tables, now, wait, history, demo, name, vision_auto, vision_departure} = snapshot;
  const count = state => tables.filter(table => table.state === state).length;
  byId('restaurant').textContent = name;
  const mode = vision_departure ? 'Vision automatique' : 'Arrivées automatiques';
  byId('mode').textContent = demo ? 'Mode démonstration' : vision_auto ? mode : 'Mode observation';
  byId('metrics').replaceChildren(metric('Tables libres', count('free')), metric('En attente', count('waiting')),
    metric('En service', count('served') + count('acknowledged')), metric('À nettoyer', count('cleaning')));
  byId('table-count').textContent = tables.length + ' tables suivies';
  byId('threshold').textContent = 'Alerte après ' + duration(wait) + ' sans prise en charge.';
  const filter = byId('filter').value;
  const visible = tables.filter(table => filter === 'all' || filter === table.state);
  const focused = document.activeElement;
  const focusedCard = focused.closest('.card')?.id;
  const signature = JSON.stringify(visible.map(({id, revision, online, observation}) => [id, revision, online, observation]));
  if (signature !== visibleSignature) {
    visibleSignature = signature;
    byId('tables').replaceChildren(...(visible.length ? visible.map(table => tableCard(table, now, demo)) : [node('p','Aucune table dans cet état.')]));
    if (focusedCard) {
      const card = byId(focusedCard);
      const replacement = [...(card?.querySelectorAll('button') || [])].find(button => button.dataset.action === focused.dataset.action);
      (replacement || card?.querySelector('button') || byId('filter')).focus({preventScroll:true});
    }
  } else {
    visible.filter(table => table.state !== 'free').forEach(table => {
      byId('table-' + table.id).querySelector('.timer').textContent =
        duration(now - (table.state === 'cleaning' ? table.changed : table.seated));
    });
  }
  const alerts = tables.filter(table => table.state === 'cleaning' || (table.state === 'waiting' && table.alerted));
  byId('alerts').replaceChildren(...(alerts.length ? alerts.map(table => {
    const cleaning = table.state === 'cleaning';
    return line('Table ' + table.id + (cleaning ? ' · À nettoyer' : ' · En attente'),
      duration(now - (cleaning ? table.changed : table.seated)), !cleaning);
  }) : [node('p','Aucune priorité pour le moment.')]));
  const format = new Intl.DateTimeFormat('fr', {hour:'2-digit',minute:'2-digit'});
  byId('history').replaceChildren(...(history.length ? history.slice(0,8).map(event =>
    line('T' + event.table_id + ' · ' + labels[event.action], format.format(event.at * 1000))) : [node('p','Aucune activité enregistrée.')]));
}
async function refresh() {
  if (updating || busy) return;
  updating = true;
  try {
    snapshot = await request('/api/snapshot');
    renderFloor();
    byId('connection').textContent = '● Serveur connecté';
  } catch {
    byId('connection').textContent = 'Serveur indisponible';
  } finally {
    updating = false;
  }
}
async function showReport() {
  const id = ++reportRequest;
  try {
    const visits = await request('/api/report');
    if (id !== reportRequest) return;
    const delays = visits.filter(visit => visit.served != null).map(visit => visit.served - visit.seated).sort((a,b) => a-b);
    const median = delays.length ? (delays[Math.floor((delays.length-1)/2)] + delays[Math.floor(delays.length/2)])/2 : null;
    byId('report-metrics').replaceChildren(metric('Sessions', visits.length),metric('Service confirmé', delays.length),
      metric('Délai médian de service', median === null ? '—' : duration(median)),metric('Alertes', visits.filter(visit => visit.alerted != null).length));
    const hours = Array(24).fill(0);
    visits.forEach(visit => hours[new Date(visit.seated * 1000).getHours()]++);
    byId('hours').replaceChildren(...hours.map((count,hour) => {
      const item = node('div', hour + ' h', 'hour');
      item.append(node('strong', count));
      return item;
    }));
  } catch (error) {
    if (id === reportRequest) notice(error.message);
  }
}
function navigate(view) {
  notice('');
  for (const section of ['floor', 'report', 'video']) {
    byId(section).hidden = view !== section;
    if (view === section) byId(section + '-tab').setAttribute('aria-current', 'page');
    else byId(section + '-tab').removeAttribute('aria-current');
  }
  if (view === 'report') showReport(); else reportRequest++;
}
byId('filter').addEventListener('change', renderFloor);
function syncView() {
  const view = location.hash.slice(1);
  navigate(['report', 'video'].includes(view) ? view : 'floor');
}
for (const section of ['floor', 'report', 'video']) {
  byId(section + '-tab').addEventListener('click', () => { location.hash = section; });
}
window.addEventListener('hashchange', syncView);
syncView();
refresh();
setInterval(refresh, 2500);
