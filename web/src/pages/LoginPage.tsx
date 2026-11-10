import { createSignal } from 'solid-js';
import { api, ApiError } from '../api/client';
import type { SessionResponse } from '../api/types';

interface LoginPageProps {
  onLoggedIn: (session: SessionResponse) => void;
}

export function LoginPage(props: LoginPageProps) {
  const [username, setUsername] = createSignal('');
  const [password, setPassword] = createSignal('');
  const [error, setError] = createSignal('');
  const [loading, setLoading] = createSignal(false);

  const submit = async (event: Event) => {
    event.preventDefault();
    setError('');
    setLoading(true);
    try {
      const session = await api.login(username(), password());
      props.onLoggedIn(session);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Login failed.';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div class="login-page">
      <header class="site-header">
        <div class="brand">
          <div class="mark">I</div>
          <div>
            <h1>IDEA Field Usage</h1>
            <p>Programme dashboard · running on idea · operator login</p>
          </div>
        </div>
      </header>
      <form class="login-card" data-testid="login-form" onSubmit={submit}>
        <h2>Operator login</h2>
        <p class="muted">
          Same operator pattern as the Console. The default password convention comes from
          server configuration and is not stored in this app.
        </p>
        <label for="username">Username</label>
        <input
          id="username"
          name="username"
          autocomplete="username"
          value={username()}
          onInput={(event) => setUsername(event.currentTarget.value)}
        />
        <label for="password">Password</label>
        <input
          id="password"
          name="password"
          type="password"
          autocomplete="current-password"
          value={password()}
          onInput={(event) => setPassword(event.currentTarget.value)}
        />
        <p class="login-error" data-testid="login-error">{error()}</p>
        <button class="btn btn-primary" type="submit" disabled={loading()}>
          {loading() ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  );
}
