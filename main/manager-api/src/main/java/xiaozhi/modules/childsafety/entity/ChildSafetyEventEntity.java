package xiaozhi.modules.childsafety.entity;

import java.util.Date;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

@Data
@TableName("ai_child_safety_event")
public class ChildSafetyEventEntity {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String agentId;
    private Long ownerUserId;
    private Long historyId;
    private String category;
    private String riskLevel;
    private Date occurredAt;
    private Date readAt;
    private Date createdAt;
}
