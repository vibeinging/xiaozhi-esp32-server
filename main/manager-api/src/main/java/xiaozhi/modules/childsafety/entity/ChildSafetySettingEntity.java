package xiaozhi.modules.childsafety.entity;

import java.util.Date;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

@Data
@TableName("ai_child_safety_setting")
public class ChildSafetySettingEntity {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String agentId;
    private Boolean enabled;
    private String reviewTime;
    private String timezone;
    private Integer chatRetentionDays;
    private Integer reportRetentionDays;
    private String previousMemModelId;
    private Integer previousChatHistoryConf;
    private Long creator;
    private Date createDate;
    private Long updater;
    private Date updateDate;
}
