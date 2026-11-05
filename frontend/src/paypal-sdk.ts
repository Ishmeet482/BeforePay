// PayPal SDK v6, sandbox origin only. Loaded solely after an explicit click.
type Session = { start: (options: { presentationMode: 'popup' }, order: Promise<{ orderId: string }>) => Promise<void> }
type Callbacks = { onApprove: (data: { orderId: string }) => Promise<void>; onCancel: () => Promise<void>; onError: () => void }
export type PayPalInstance = {
  findEligibleMethods: (options: { currencyCode: string; amount: string }) => Promise<{ isEligible: (method: string) => boolean }>
  createPayPalOneTimePaymentSession: (options: Callbacks) => Session
}
declare global { interface Window { paypal?: { createInstance: (options: { clientId: string; components: string[]; pageType: string }) => Promise<PayPalInstance> } } }
const SANDBOX_SDK = 'https://www.sandbox.paypal.com/web-sdk/v6/core'
let loaded: Promise<void> | undefined
export async function sandboxSdk(clientId: string): Promise<PayPalInstance> {
  if (!loaded) loaded = new Promise<void>((resolve, reject) => {
    // Do not reuse an SDK from another environment or an arbitrary browser URL.
    if (document.querySelector('script[src*="paypal.com"]:not([data-contextkey-sandbox])')) { reject(new Error('Another PayPal SDK is loaded. Reload a clean page.')); return }
    const script = document.createElement('script')
    script.src = SANDBOX_SDK; script.dataset.contextkeySandbox = 'true'; script.async = true
    script.onload = () => window.paypal?.createInstance ? resolve() : reject(new Error('Sandbox SDK unavailable.'))
    script.onerror = () => { script.remove(); loaded = undefined; reject(new Error('Could not load PayPal sandbox SDK.')) }
    document.head.append(script)
  })
  await loaded
  if (!window.paypal) throw new Error('PayPal sandbox SDK unavailable.')
  return window.paypal.createInstance({ clientId, components: ['paypal-payments'], pageType: 'checkout' })
}
