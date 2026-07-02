/* Minimal API client. Token lives in localStorage; 401 kicks back to login. */
const API = {
  token() { return localStorage.getItem('pg_token'); },
  setToken(t) { t ? localStorage.setItem('pg_token', t) : localStorage.removeItem('pg_token'); },

  async request(method, path, body, isForm = false) {
    const headers = { 'Authorization': `Bearer ${this.token()}` };
    let payload = body;
    if (body && !isForm) {
      headers['Content-Type'] = 'application/json';
      payload = JSON.stringify(body);
    }
    const res = await fetch(path, { method, headers, body: payload });
    if (res.status === 401 && !path.endsWith('/auth/login')) {
      this.setToken(null);
      location.hash = '#/login';
      throw new Error('Session expired');
    }
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch (_) { /* not json */ }
      throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    }
    if (res.status === 204) return null;
    return res.json();
  },

  get(path) { return this.request('GET', path); },
  post(path, body) { return this.request('POST', path, body); },
  postForm(path, formData) { return this.request('POST', path, formData, true); },
  patch(path, body) { return this.request('PATCH', path, body); },
  del(path) { return this.request('DELETE', path); },

  /* image/stream URLs need the token as a query param (<img> can't set headers) */
  streamUrl(cameraId, overlay = true) {
    return `/api/cameras/${cameraId}/stream?overlay=${overlay ? 1 : 0}&token=${this.token()}`;
  },
  snapshotUrl(cameraId, overlay = false) {
    return `/api/cameras/${cameraId}/snapshot?overlay=${overlay ? 1 : 0}&token=${this.token()}&_=${Date.now()}`;
  },
};
