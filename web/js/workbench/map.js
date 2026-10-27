/**
 * AquaSphere Workbench SVG Map Renderer
 * Linear mapping of 720x440 viewBox to 45–105°E and 30–5°N.
 */

const LON_MIN = 45.0;
const LON_MAX = 105.0;
const LAT_MIN = 5.0;
const LAT_MAX = 30.0;
const WIDTH = 720;
const HEIGHT = 440;

export function lonToX(lon) {
  return ((lon - LON_MIN) / (LON_MAX - LON_MIN)) * WIDTH;
}

export function latToY(lat) {
  return ((LAT_MAX - lat) / (LAT_MAX - LAT_MIN)) * HEIGHT;
}

export function xToLon(x) {
  const lon = LON_MIN + (x / WIDTH) * (LON_MAX - LON_MIN);
  return Math.max(LON_MIN, Math.min(LON_MAX, Math.round(lon * 10) / 10));
}

export function yToLat(y) {
  const lat = LAT_MAX - (y / HEIGHT) * (LAT_MAX - LAT_MIN);
  return Math.max(LAT_MIN, Math.min(LAT_MAX, Math.round(lat * 10) / 10));
}

export function initMap(svgEl, onSelectLocation) {
  if (!svgEl) return;

  svgEl.addEventListener('click', (e) => {
    const pt = svgEl.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const svgP = pt.matrixTransform(svgEl.getScreenCTM().inverse());

    const lat = yToLat(svgP.y);
    const lon = xToLon(svgP.x);

    setSelectedPin(lat, lon);
    if (typeof onSelectLocation === 'function') {
      onSelectLocation(lat, lon);
    }
  });
}

export function setSelectedPin(lat, lon) {
  const pin = document.getElementById('map-selected-pin');
  if (!pin) return;
  const x = lonToX(lon);
  const y = latToY(lat);
  pin.setAttribute('transform', `translate(${x.toFixed(1)}, ${y.toFixed(1)})`);
}

export function setArgoMarkers(profiles, onMarkerClick) {
  const group = document.getElementById('map-argo-group');
  if (!group) return;

  group.innerHTML = '';
  if (!profiles || !profiles.length) {
    // Default schematic markers from reference
    group.innerHTML = `
      <circle cx="190" cy="250" r="5" class="map-point-hover"/>
      <circle cx="260" cy="330" r="5" class="map-point-hover"/>
      <circle cx="510" cy="262" r="5" class="map-point-hover"/>
      <circle cx="560" cy="330" r="5" class="map-point-hover"/>
    `;
    return;
  }

  profiles.forEach(p => {
    const cx = lonToX(p.lon);
    const cy = latToY(p.lat);
    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('cx', cx.toFixed(1));
    circle.setAttribute('cy', cy.toFixed(1));
    circle.setAttribute('r', '5');
    circle.setAttribute('class', 'map-point-hover');
    circle.setAttribute('cursor', 'pointer');
    circle.innerHTML = `<title>Float #${p.float_id || p.id} (${p.lat}°N, ${p.lon}°E)</title>`;

    if (onMarkerClick) {
      circle.addEventListener('click', (e) => {
        e.stopPropagation();
        onMarkerClick(p.lat, p.lon);
      });
    }
    group.appendChild(circle);
  });
}
