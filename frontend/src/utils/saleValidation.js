export const saleInformationError = (data, requireDate = false) => {
  if (!data.sale_customer?.trim()) return '请填写出售客户'
  if (data.sale_price == null || data.sale_price === '' || !Number.isFinite(Number(data.sale_price)) || Number(data.sale_price) < 0) return '请填写有效的出售金额'
  if (requireDate && !data.sale_date) return '请填写出售日期'
  if (!data.sellers?.length) return '请选择出售人'
  return ''
}
