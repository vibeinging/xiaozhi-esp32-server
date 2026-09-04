package xiaozhi.modules.childsafety.controller;

import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.childsafety.dto.ChildSafetyDashboardDTO;
import xiaozhi.modules.childsafety.dto.ChildSafetyReviewViewDTO;
import xiaozhi.modules.childsafety.dto.ChildSafetySettingDTO;
import xiaozhi.modules.childsafety.service.ChildSafetyReviewService;
import xiaozhi.modules.security.user.SecurityUser;

@Tag(name = "家长儿童安全中心")
@RestController
@RequestMapping("/child-safety")
@RequiredArgsConstructor
@RequiresPermissions("sys:role:normal")
public class ChildSafetyController {
    private final ChildSafetyReviewService childSafetyReviewService;

    @GetMapping("/dashboard")
    @Operation(summary = "获取当前家长的安全日报和即时风险")
    public Result<ChildSafetyDashboardDTO> dashboard() {
        return new Result<ChildSafetyDashboardDTO>().ok(
                childSafetyReviewService.getDashboard(SecurityUser.getUserId()));
    }

    @GetMapping("/settings/{agentId}")
    @Operation(summary = "获取智能体的每日安全复查设置")
    public Result<ChildSafetySettingDTO> getSetting(@PathVariable String agentId) {
        return new Result<ChildSafetySettingDTO>().ok(
                childSafetyReviewService.getSetting(agentId, SecurityUser.getUserId()));
    }

    @PutMapping("/settings/{agentId}")
    @Operation(summary = "更新智能体的每日安全复查设置")
    public Result<ChildSafetySettingDTO> updateSetting(@PathVariable String agentId,
            @Valid @RequestBody ChildSafetySettingDTO dto) {
        return new Result<ChildSafetySettingDTO>().ok(
                childSafetyReviewService.updateSetting(agentId, SecurityUser.getUserId(), dto));
    }

    @PostMapping("/reviews/{id}/read")
    @Operation(summary = "把安全日报标为已读")
    public Result<Boolean> markReviewRead(@PathVariable Long id) {
        childSafetyReviewService.markReviewRead(id, SecurityUser.getUserId());
        return new Result<Boolean>().ok(true);
    }

    @PostMapping("/events/{id}/read")
    @Operation(summary = "把即时风险标为已读")
    public Result<Boolean> markEventRead(@PathVariable Long id) {
        childSafetyReviewService.markEventRead(id, SecurityUser.getUserId());
        return new Result<Boolean>().ok(true);
    }

    @PostMapping("/reviews/run/{agentId}")
    @Operation(summary = "立即复查当前智能体今天的聊天")
    public Result<ChildSafetyReviewViewDTO> runReview(@PathVariable String agentId) {
        return new Result<ChildSafetyReviewViewDTO>().ok(
                childSafetyReviewService.reviewNow(agentId, SecurityUser.getUserId()));
    }
}
