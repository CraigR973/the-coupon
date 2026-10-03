import * as React from 'react';
import * as DialogPrimitive from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

type DialogProps = React.ComponentPropsWithoutRef<typeof DialogPrimitive.Root> & {
  /**
   * Controlled dialogs have no Radix trigger for focus restoration. Callers pass the
   * control that opened them here; the shared content wrapper returns focus on every
   * close path, including Escape, overlay clicks and the close button.
   */
  restoreFocusRef?: React.RefObject<HTMLElement | null>;
};

const DialogFocusRestoreContext = React.createContext<
  React.RefObject<HTMLElement | null> | undefined
>(undefined);

function Dialog({ restoreFocusRef, ...props }: DialogProps) {
  return (
    <DialogFocusRestoreContext.Provider value={restoreFocusRef}>
      <DialogPrimitive.Root {...props} />
    </DialogFocusRestoreContext.Provider>
  );
}
const DialogTrigger = DialogPrimitive.Trigger;
const DialogPortal = DialogPrimitive.Portal;
const DialogClose = DialogPrimitive.Close;

const DialogOverlay = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={cn(
      'fixed inset-0 z-modal bg-black/70 backdrop-blur-sm',
      'data-[state=open]:animate-in data-[state=closed]:animate-out',
      'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
      className,
    )}
    {...props}
  />
));
DialogOverlay.displayName = DialogPrimitive.Overlay.displayName;

const DialogContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>
>(({ className, children, onCloseAutoFocus, ...props }, ref) => {
  const restoreFocusRef = React.useContext(DialogFocusRestoreContext);

  return (
    <DialogPortal>
      <DialogOverlay />
      <DialogPrimitive.Content
        ref={ref}
        onCloseAutoFocus={(event) => {
          onCloseAutoFocus?.(event);
          if (event.defaultPrevented) return;
          const trigger = restoreFocusRef?.current;
          if (!trigger?.isConnected) return;
          event.preventDefault();
          trigger.focus();
        }}
        className={cn(
          'fixed left-[50%] top-[50%] z-modal w-[calc(100%-2rem)] max-w-lg translate-x-[-50%] translate-y-[-50%]',
          'border border-border bg-surface-elevated p-6 shadow-lg rounded-xl',
          'data-[state=open]:animate-in data-[state=closed]:animate-out',
          'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
          'data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95',
          className,
        )}
        {...props}
      >
        {children}
        <DialogClose className="absolute right-4 top-4 rounded-sm tap-target inline-flex items-center justify-center opacity-70 hover:opacity-100 focus:outline-none focus-visible:shadow-glow press-down">
          <X className="h-5 w-5 text-text-secondary" />
          <span className="sr-only">Close</span>
        </DialogClose>
      </DialogPrimitive.Content>
    </DialogPortal>
  );
});
DialogContent.displayName = DialogPrimitive.Content.displayName;

function DialogHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('flex flex-col space-y-1.5 text-center sm:text-left', className)} {...props} />
  );
}
DialogHeader.displayName = 'DialogHeader';

function DialogFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('flex flex-col-reverse gap-2 sm:flex-row sm:justify-end sm:space-x-2', className)}
      {...props}
    />
  );
}
DialogFooter.displayName = 'DialogFooter';

const DialogTitle = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    className={cn('text-lg font-semibold text-text-primary font-sans tracking-tight', className)}
    {...props}
  />
));
DialogTitle.displayName = DialogPrimitive.Title.displayName;

const DialogDescription = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Description
    ref={ref}
    className={cn('text-sm text-text-secondary font-sans', className)}
    {...props}
  />
));
DialogDescription.displayName = DialogPrimitive.Description.displayName;

export {
  Dialog,
  DialogPortal,
  DialogOverlay,
  DialogTrigger,
  DialogClose,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
};
