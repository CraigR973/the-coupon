import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { ThemeProvider, useTheme } from '@/contexts/ThemeContext';

function ThemeControls() {
  const { setMode } = useTheme();
  return <button onClick={() => setMode('light')}>Use light theme</button>;
}

afterEach(() => {
  document.querySelectorAll('meta[name="theme-color"][data-theme]').forEach((meta) => meta.remove());
  localStorage.removeItem('coupon_theme');
});

it('updates the active status-bar colour when the member switches theme without reloading', async () => {
  for (const [theme, colour] of [['dark', '#0B0E13'], ['light', '#F7F8FA']]) {
    const meta = document.createElement('meta');
    meta.name = 'theme-color';
    meta.setAttribute('data-theme', theme);
    meta.content = colour;
    document.head.append(meta);
  }
  render(<ThemeProvider><ThemeControls /></ThemeProvider>);
  const dark = document.querySelector('meta[data-theme="dark"]')!;
  const light = document.querySelector('meta[data-theme="light"]')!;
  expect(dark.getAttribute('media')).toBe('all');
  expect(light.getAttribute('media')).toBe('not all');

  fireEvent.click(screen.getByRole('button', { name: 'Use light theme' }));
  await waitFor(() => expect(document.documentElement.classList.contains('light')).toBe(true));
  expect(dark.getAttribute('media')).toBe('not all');
  expect(light.getAttribute('media')).toBe('all');
  expect(light.getAttribute('content')).toBe('#F7F8FA');
});
