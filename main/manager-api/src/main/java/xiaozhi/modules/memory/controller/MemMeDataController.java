package xiaozhi.modules.memory.controller;

import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import lombok.AllArgsConstructor;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.memory.service.MemMeDataService;
import xiaozhi.modules.security.user.SecurityUser;

@RestController
@AllArgsConstructor
@RequestMapping("/memory/memme")
public class MemMeDataController {
    private static final String DELETE_CONFIRMATION = "DELETE-ALL-MEMORY";

    private final MemMeDataService memMeDataService;

    @GetMapping("/export")
    @RequiresPermissions("sys:role:normal")
    public ResponseEntity<byte[]> exportMyMemory() {
        byte[] export = memMeDataService.exportUserData(SecurityUser.getUserId());
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .header(
                        HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=memme-export.json")
                .body(export);
    }

    @DeleteMapping("/all")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> deleteMyMemory(@RequestParam("confirm") String confirm) {
        if (!DELETE_CONFIRMATION.equals(confirm)) {
            throw new RenException("删除确认文字不正确");
        }
        memMeDataService.clearUserData(SecurityUser.getUserId());
        return new Result<Void>().ok(null);
    }
}
