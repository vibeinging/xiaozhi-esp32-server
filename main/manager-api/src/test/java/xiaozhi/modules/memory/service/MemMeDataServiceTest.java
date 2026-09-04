package xiaozhi.modules.memory.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.InetSocketAddress;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;

import xiaozhi.common.exception.RenException;

class MemMeDataServiceTest {

    @Test
    void exportUsesStableServerSideUserIdAndBearerToken() throws Exception {
        AtomicReference<String> request = new AtomicReference<>();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/internal/memme/users/", exchange -> {
            request.set(
                    exchange.getRequestMethod()
                            + " " + exchange.getRequestURI()
                            + " " + exchange.getRequestHeaders().getFirst("Authorization"));
            byte[] body = "{\"success\":true,\"data\":{}}".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        server.start();
        try {
            MemMeDataService service = new MemMeDataService(
                    HttpClient.newHttpClient(),
                    new ObjectMapper(),
                    "test-key",
                    "http://127.0.0.1:" + server.getAddress().getPort()
                            + "/internal/memme/users/");

            byte[] exported = service.exportUserData(42L);

            assertEquals(
                    "POST /internal/memme/users/xiaozhi-user-42/export Bearer test-key",
                    request.get());
            assertEquals("{}", new String(exported, StandardCharsets.UTF_8));
            assertTrue(service.isConfigured());

            service.clearUserData(42L);
            assertEquals(
                    "DELETE /internal/memme/users/xiaozhi-user-42?allow_future=true Bearer test-key",
                    request.get());
        } finally {
            server.stop(0);
        }
    }

    @Test
    void missingKeyFailsClosedBeforeNetworkRequest() {
        MemMeDataService service = new MemMeDataService(
                HttpClient.newHttpClient(), new ObjectMapper(), "", "http://127.0.0.1:1/");

        assertFalse(service.isConfigured());
        assertThrows(RenException.class, () -> service.deleteUserData(1L));
    }
}
