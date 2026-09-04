import { getServiceUrl } from '../api'
import RequestService from '../httpRequest'

export default {
  exportMemMeData(callback, failCallback) {
    RequestService.sendRequest()
      .url(`${getServiceUrl()}/memory/memme/export`)
      .method('GET')
      .type('blob')
      .success((res) => {
        RequestService.clearRequestTime()
        callback(res)
      })
      .fail((error) => {
        RequestService.clearRequestTime()
        failCallback(error)
      })
      .networkFail((error) => {
        RequestService.clearRequestTime()
        failCallback(error)
      })
      .send()
  },

  deleteAllMemMeData(callback, failCallback) {
    RequestService.sendRequest()
      .url(`${getServiceUrl()}/memory/memme/all?confirm=DELETE-ALL-MEMORY`)
      .method('DELETE')
      .success((res) => {
        RequestService.clearRequestTime()
        callback(res)
      })
      .fail((error) => {
        RequestService.clearRequestTime()
        failCallback(error)
      })
      .networkFail((error) => {
        RequestService.clearRequestTime()
        failCallback(error)
      })
      .send()
  }
}
