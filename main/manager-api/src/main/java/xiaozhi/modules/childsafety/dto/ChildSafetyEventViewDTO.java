package xiaozhi.modules.childsafety.dto;

import java.util.Date;

import lombok.Data;

@Data
public class ChildSafetyEventViewDTO {
    private Long id;
    private String agentId;
    private String category;
    private String riskLevel;
    private Date occurredAt;
    private Date readAt;
}
