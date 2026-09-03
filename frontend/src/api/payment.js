import request from '../utils/request'

export async function createCheckoutSession(planType = 'monthly') {
  const { data } = await request.post('/payment/create-checkout', {
    plan_type: planType,
  })
  return data
}

export async function getOrders() {
  const { data } = await request.get('/payment/orders')
  return data
}
