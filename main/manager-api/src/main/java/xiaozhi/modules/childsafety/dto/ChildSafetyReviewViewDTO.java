package xiaozhi.modules.childsafety.dto;

import java.time.LocalDate;
import java.util.Date;
import java.util.List;
import java.util.Map;

import lombok.Data;

@Data
public class ChildSafetyReviewViewDTO {
    private Long id;
    private String agentId;
    private LocalDate reviewDate;
    private Integer messageCount;
    private String riskLevel;
    private Integer riskCount;
    private String summary;
    private List<Map<String, Object>> details;
    private String parentAdvice;
    private String status;
    private Date readAt;
    private Date reviewedAt;
}
