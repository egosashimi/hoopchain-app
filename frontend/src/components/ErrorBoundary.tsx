// ============================================================
// HOOPCHAIN — ErrorBoundary
// Catches uncaught React render errors and shows a recovery UI.
// Class component required — no hooks equivalent for componentDidCatch.
// ============================================================

import React from 'react';

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends React.Component<React.PropsWithChildren, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[Hoopchain] Uncaught error:', error, info.componentStack);
  }

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-hc-bg gap-5 text-center p-6">
        <div style={{ fontSize: '3rem' }}>🏀</div>
        <h1 className="font-display text-2xl font-bold text-hc-text">
          Something went wrong
        </h1>
        <p className="text-hc-text-2 text-sm max-w-sm">
          An unexpected error occurred. Refreshing usually fixes it.
        </p>
        {this.state.error && (
          <pre
            className="text-hc-text-3 text-xs font-mono bg-hc-surface border border-hc-border rounded-hc p-3 max-w-md w-full overflow-x-auto text-left"
            style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}
          >
            {this.state.error.message}
          </pre>
        )}
        <button
          onClick={() => window.location.reload()}
          className="btn btn-primary mt-1"
        >
          Reload game
        </button>
      </div>
    );
  }
}
