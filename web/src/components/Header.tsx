import type { JSX } from 'solid-js';
import { Show } from 'solid-js';

interface HeaderProps {
  weekLabel: string;
  headerTimeZone: string;
  username: string;
  onLogout: () => void;
  weekPicker?: JSX.Element;
}

export function Header(props: HeaderProps) {
  return (
    <header class="site-header">
      <div class="brand">
        <div class="mark">I</div>
        <div>
          <h1>IDEA Field Usage</h1>
          <p>Programme dashboard · running on idea · against the teacher tutorial</p>
        </div>
      </div>
      <div class="header-meta">
        <strong>{props.weekLabel || 'Select a week'}</strong>
        Stored only on idea · role-level counts, no names · {props.headerTimeZone}
        <div class="header-actions">
          {props.weekPicker}
          <span class="header-user">{props.username}</span>
          <button class="btn btn-quiet" type="button" onClick={() => props.onLogout()}>Log out</button>
        </div>
      </div>
    </header>
  );
}

export function SampleNote() {
  return (
    <div class="sample-note" data-testid="sample-data-note">
      Sample data — illustrative numbers, not real measurements from field kits.
    </div>
  );
}

interface FooterProps {
  versionLabel?: string | null;
}

export function Footer(props: FooterProps) {
  return (
    <footer class="site-footer">
      <div>IDEA Field Usage · dashboard App on <span>idea</span> · data store on idea only</div>
      <Show when={props.versionLabel}>
        {(label) => (
          <div class="site-footer__version" data-testid="app-version">{label()}</div>
        )}
      </Show>
      <div>No data never counts against a school · the dashboard informs a human decision</div>
    </footer>
  );
}

