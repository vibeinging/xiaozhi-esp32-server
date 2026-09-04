package xiaozhi.modules.childsafety.dto;

import java.util.List;

import lombok.Data;

@Data
public class ChildSafetyDashboardDTO {
    private long unreadCount;
    private List<ChildSafetyEventViewDTO> events;
    private List<ChildSafetyReviewViewDTO> reviews;
}
