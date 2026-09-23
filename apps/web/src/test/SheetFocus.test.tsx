import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { useRef, useState } from 'react';
import { Sheet } from '@/components/ui/sheet';

/**
 * UX-16. Closing the bottom-navigation "More" sheet with Escape left focus on
 * `<body>`, so the next Tab started again from the top of the document.
 *
 * The cause is not Radix: Radix restores focus to its own `Dialog.Trigger`, and
 * this sheet has none — callers own `open` and render their own button — so there
 * was nothing for it to restore to. The account menu is a Radix dropdown with a
 * real trigger, which is exactly why it never had the defect and was the model.
 */
function Harness({ withTrigger }: { withTrigger: boolean }) {
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  return (
    <>
      <button ref={trigger} type="button" onClick={() => setOpen(true)}>
        More
      </button>
      <Sheet
        open={open}
        onClose={() => setOpen(false)}
        title="More"
        triggerRef={withTrigger ? trigger : undefined}
      >
        <button type="button">Settings</button>
      </Sheet>
    </>
  );
}

describe('Sheet focus return', () => {
  it('puts focus back on the control that opened it when Escape closes it', async () => {
    render(<Harness withTrigger />);
    const trigger = screen.getByRole('button', { name: 'More' });
    fireEvent.click(trigger);

    const dialog = await screen.findByRole('dialog');
    fireEvent.keyDown(dialog, { key: 'Escape' });

    await screen.findByRole('button', { name: 'More' });
    expect(document.activeElement).toBe(trigger);
    expect(document.activeElement).not.toBe(document.body);
  });

  it('returns focus the same way when the sheet is closed by its own button', async () => {
    render(<Harness withTrigger />);
    const trigger = screen.getByRole('button', { name: 'More' });
    fireEvent.click(trigger);

    fireEvent.click(await screen.findByRole('button', { name: 'Close' }));

    await screen.findByRole('button', { name: 'More' });
    expect(document.activeElement).toBe(trigger);
  });

  it('leaves Radix in charge when no trigger is named', async () => {
    // The prop is optional, so the sheet must not start reaching for a focus target
    // that a caller never gave it.
    render(<Harness withTrigger={false} />);
    fireEvent.click(screen.getByRole('button', { name: 'More' }));
    const dialog = await screen.findByRole('dialog');
    expect(() => fireEvent.keyDown(dialog, { key: 'Escape' })).not.toThrow();
  });
});
