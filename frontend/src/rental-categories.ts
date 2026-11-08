// Creation guidance only. Never persisted as equipment, evidence or agreement terms.
export const rentalCategories = {
  camera: { label: 'Camera & photography', example: 'Camera kit · location shoot' },
  audio: { label: 'Audio equipment', example: 'Wireless PA & microphones · conference' },
  lighting: { label: 'Lighting equipment', example: 'LED lighting kit · studio session' },
  presentation: { label: 'Projectors & presentation equipment', example: 'Projector & screen · workshop' },
  custom: { label: 'Other / custom equipment', example: 'Describe your equipment and rental occasion' },
}
export type RentalCategory = keyof typeof rentalCategories
