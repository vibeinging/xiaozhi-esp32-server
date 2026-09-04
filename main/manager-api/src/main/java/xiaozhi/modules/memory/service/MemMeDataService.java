package xiaozhi.modules.memory.service;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import xiaozhi.common.exception.RenException;

@Service
public class MemMeDataService {
    private static final String INTERNAL_BASE_URL = "http://127.0.0.1:8003/internal/memme/users/";

    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;
    private final String apiKey;
    private final String internalBaseUrl;

    @Autowired
    public MemMeDataService(ObjectMapper objectMapper) {
        this(
                HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build(),
                objectMapper,
                System.getenv("MEMME_API_KEY"),
                INTERNAL_BASE_URL);
    }

    MemMeDataService(
            HttpClient httpClient, ObjectMapper objectMapper, String apiKey, String internalBaseUrl) {
        this.httpClient = httpClient;
        this.objectMapper = objectMapper;
        this.apiKey = apiKey == null ? "" : apiKey.trim();
        this.internalBaseUrl = internalBaseUrl;
    }

    public byte[] exportUserData(Long userId) {
        return request(userId, "/export", "POST");
    }

    public boolean isConfigured() {
        return !apiKey.isBlank();
    }

    public void deleteUserData(Long userId) {
        request(userId, "", "DELETE");
    }

    public void clearUserData(Long userId) {
        request(userId, "?allow_future=true", "DELETE");
    }

    private byte[] request(Long userId, String suffix, String method) {
        if (userId == null || userId <= 0 || apiKey.isBlank()) {
            throw new RenException("长期记忆服务未正确配置");
        }
        String stableUserId = "xiaozhi-user-" + userId;
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(internalBaseUrl + stableUserId + suffix))
                .timeout(Duration.ofSeconds(15))
                .header("Authorization", "Bearer " + apiKey)
                .header("Accept", "application/json")
                .method(method, HttpRequest.BodyPublishers.noBody())
                .build();
        try {
            HttpResponse<byte[]> response = httpClient.send(
                    request, HttpResponse.BodyHandlers.ofByteArray());
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new RenException("长期记忆服务暂时不可用");
            }
            JsonNode envelope = objectMapper.readTree(response.body());
            if (!envelope.path("success").asBoolean(false)) {
                throw new RenException("长期记忆操作未完成");
            }
            JsonNode data = envelope.get("data");
            if (data == null || data.isMissingNode()) {
                throw new RenException("长期记忆服务返回了无效数据");
            }
            return objectMapper.writeValueAsBytes(data);
        } catch (RenException error) {
            throw error;
        } catch (Exception error) {
            throw new RenException("长期记忆服务暂时不可用", error);
        }
    }
}
