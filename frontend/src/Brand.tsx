import monogram from './assets/beforepay-monogram.svg'

/** Wordmark supplies the accessible name; the paired image is decorative. */
export default function Brand() {
  return <><img className="brand-mark" src={monogram} width={34} height={34} alt="" aria-hidden="true" /><span>BeforePay</span></>
}
