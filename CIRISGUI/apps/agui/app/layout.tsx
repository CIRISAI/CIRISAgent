import './globals.css';
import type { ReactNode } from 'react';
import Link from 'next/link';

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <aside className="sidebar">
          <h2>CIRIS</h2>
          <nav>
            <ul>
              <li><Link href="/">Home</Link></li>
              <li><Link href="/audit">Audit</Link></li>
              <li><Link href="/comms">Communications</Link></li>
              <li><Link href="/memory">Memory</Link></li>
              <li><Link href="/tools">Tools</Link></li>
              <li><Link href="/runtime">Runtime Control</Link></li>
              <li><Link href="/system">System Status</Link></li>
              <li><Link href="/config">Configuration</Link></li>
              <li><Link href="/services">Services</Link></li>
              <li><Link href="/wa">WA</Link></li>
              <li><Link href="/logs">Logs</Link></li>
            </ul>
          </nav>
        </aside>
        <main>{children}</main>
      </body>
    </html>
  );
}
