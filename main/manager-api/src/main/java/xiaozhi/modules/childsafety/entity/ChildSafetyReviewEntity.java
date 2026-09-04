package xiaozhi.modules.childsafety.entity;

import java.time.LocalDate;
import java.util.Date;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

@Data
@TableName("ai_child_safety_review")
public class ChildSafetyReviewEntity {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String agentId;
    private Long ownerUserId;
    private LocalDate reviewDate;
    private Date reviewStartAt;
    private Date reviewEndAt;
    private Integer messageCount;
    private String riskLevel;
    private Integer riskCount;
    private String summary;
    private String detailsJson;
    private String parentAdvice;
    private String status;
    private Date readAt;
    private String lastError;
    private Integer attemptCount;
    private Date reviewedAt;
    private Date createdAt;
    private Date updatedAt;
}
