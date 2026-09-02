import { getServiceUrl } from '../api';
import RequestService from '../httpRequest';

function request(path, method, data, callback, failure) {
  const target = RequestService.sendRequest()
    .url(`${getServiceUrl()}${path}`)
    .method(method)
    .data(data || {})
    .success((res) => {
      RequestService.clearRequestTime();
      callback(res);
    })
    .networkFail((error) => {
      RequestService.clearRequestTime();
      if (failure) failure(error);
    });
  if (failure) target.fail(failure);
  target.send();
}

export default {
  getDashboard(callback, failure) {
    request('/child-safety/dashboard', 'GET', null, callback, failure);
  },
  getSetting(agentId, callback, failure) {
    request(`/child-safety/settings/${agentId}`, 'GET', null, callback, failure);
  },
  updateSetting(agentId, data, callback, failure) {
    request(`/child-safety/settings/${agentId}`, 'PUT', data, callback, failure);
  },
  runReview(agentId, callback, failure) {
    request(`/child-safety/reviews/run/${agentId}`, 'POST', null, callback, failure);
  },
  markReviewRead(id, callback, failure) {
    request(`/child-safety/reviews/${id}/read`, 'POST', null, callback, failure);
  },
  markEventRead(id, callback, failure) {
    request(`/child-safety/events/${id}/read`, 'POST', null, callback, failure);
  },
};
